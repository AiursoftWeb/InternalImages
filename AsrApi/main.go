package main

import (
	"context"
	"embed"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"log"
	"math/rand"
	"mime/multipart"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/joho/godotenv"
)

//go:embed web/dist
var distFS embed.FS

const maxUploadSize = 100 << 20

type upstream struct {
	url   string
	model string
	token string
}

type TaskStatus string

const (
	StatusPending   TaskStatus = "pending"
	StatusRunning   TaskStatus = "running"
	StatusCompleted TaskStatus = "completed"
	StatusFailed    TaskStatus = "failed"
	StatusCancelled TaskStatus = "cancelled"
)

type ASRTask struct {
	ID        string     `json:"id"`
	Status    TaskStatus `json:"status"`
	Model     string     `json:"model"`
	Level     string     `json:"level"`
	Language  string     `json:"language"`
	Filename  string     `json:"filename"`
	CreatedAt time.Time  `json:"created_at"`

	TempFilePath   string             `json:"-"`
	ResponseFormat string             `json:"-"`
	ResultChan     chan ASRTaskResult `json:"-"`
	Ctx            context.Context    `json:"-"`
	CancelFunc     context.CancelFunc `json:"-"`
}

type ASRTaskResult struct {
	StatusCode int
	Body       []byte
	Header     http.Header
	Err        error
}

type TaskManager struct {
	mu     sync.RWMutex
	tasks  map[string]*ASRTask
	queues map[string]*taskQueue
}

type taskQueue struct {
	pending  []*ASRTask
	capacity int
	notify   chan struct{}
}

func NewTaskManager(queueSize int, models map[string]upstream) *TaskManager {
	manager := &TaskManager{
		tasks:  make(map[string]*ASRTask),
		queues: make(map[string]*taskQueue, len(models)),
	}
	for model := range models {
		manager.queues[model] = &taskQueue{
			pending:  make([]*ASRTask, 0, queueSize),
			capacity: queueSize,
			notify:   make(chan struct{}, 1),
		}
	}
	return manager
}

func (tm *TaskManager) Add(task *ASRTask) error {
	tm.mu.Lock()
	defer tm.mu.Unlock()
	if _, exists := tm.tasks[task.ID]; exists {
		return fmt.Errorf("task %s already exists", task.ID)
	}
	queue, exists := tm.queues[task.Model]
	if !exists {
		return fmt.Errorf("model %s does not have a task queue", task.Model)
	}
	if len(queue.pending) >= queue.capacity {
		return fmt.Errorf("task queue is full, please try again later")
	}
	tm.tasks[task.ID] = task
	queue.pending = append(queue.pending, task)
	select {
	case queue.notify <- struct{}{}:
	default:
	}
	log.Printf("[Queue] Task %s added to queue. Filename: %s, Model: %s, Level: %s (Queue size: %d)", task.ID, task.Filename, task.Model, task.Level, len(queue.pending))
	return nil
}

func (tm *TaskManager) Cancel(id string, cancelUpstreamFunc func(model, taskID string)) bool {
	tm.mu.Lock()
	task, ok := tm.tasks[id]
	if !ok {
		tm.mu.Unlock()
		return false
	}
	if task.Status == StatusCompleted || task.Status == StatusFailed || task.Status == StatusCancelled {
		tm.mu.Unlock()
		return false
	}
	prevStatus := task.Status
	task.Status = StatusCancelled
	delete(tm.tasks, id)
	if prevStatus == StatusPending {
		tm.removePendingTask(task)
	}
	log.Printf("[Queue] Task %s is cancelled. Previous status: %s", id, prevStatus)
	if prevStatus == StatusRunning {
		if task.CancelFunc != nil {
			task.CancelFunc()
		}
		tm.mu.Unlock()
		if cancelUpstreamFunc != nil {
			cancelUpstreamFunc(task.Model, task.ID)
		}
	} else {
		tm.mu.Unlock()
		removeTemporaryFile(task.TempFilePath)
	}
	select {
	case task.ResultChan <- ASRTaskResult{
		StatusCode: http.StatusBadRequest,
		Body:       []byte(`{"error":"Task was cancelled"}`),
		Err:        errors.New("task was cancelled"),
	}:
	default:
	}
	return true
}

func (tm *TaskManager) removePendingTask(task *ASRTask) {
	queue := tm.queues[task.Model]
	for index, pendingTask := range queue.pending {
		if pendingTask.ID != task.ID {
			continue
		}
		copy(queue.pending[index:], queue.pending[index+1:])
		lastIndex := len(queue.pending) - 1
		queue.pending[lastIndex] = nil
		queue.pending = queue.pending[:lastIndex]
		return
	}
}

type service struct {
	token                 string
	upstreams             map[string]upstream
	client                *http.Client
	statusClient          *http.Client
	whisperxEnabled       bool
	funasrEnabled         bool
	funasrRealtimeEnabled bool
	whisperxSingleModel   bool
	taskManager           *TaskManager
	uploadSem             chan struct{}
}

func main() {
	if err := loadDotenv(".env"); err != nil {
		log.Fatal(err)
	}

	server, err := newServiceFromEnvironment()
	if err != nil {
		log.Fatal(err)
	}

	router := newRouter(server)

	if err := router.Run(":" + environmentOrDefault("PORT", "8080")); err != nil {
		log.Fatal(err)
	}
}

func loadDotenv(filename string) error {
	if err := godotenv.Load(filename); err != nil && !errors.Is(err, os.ErrNotExist) {
		return err
	}
	return nil
}

func newRouter(server *service) *gin.Engine {
	router := gin.New()
	router.Use(gin.Logger(), gin.Recovery())
	dist, err := fs.Sub(distFS, "web/dist")
	if err != nil {
		log.Fatal(err)
	}
	assetsFS, err := fs.Sub(dist, "assets")
	if err != nil {
		log.Fatal(err)
	}
	router.StaticFS("/assets", http.FS(assetsFS))
	router.GET("/", func(c *gin.Context) {
		data, err := fs.ReadFile(dist, "index.html")
		if err != nil {
			c.Status(http.StatusInternalServerError)
			return
		}
		c.Data(http.StatusOK, "text/html; charset=utf-8", data)
	})
	router.GET("/healthz", server.health)
	router.GET("/config", server.getConfig)
	v1 := router.Group("/v1")
	v1.Use(server.authenticate)
	v1.GET("/models", server.models)
	v1.GET("/system", server.system)
	v1.POST("/audio/transcriptions", server.transcribe)
	v1.POST("/tasks/cancel", server.cancelTask)
	v1.POST("/tasks/:id/cancel", server.cancelTask)
	return router
}

func newServiceFromEnvironment() (*service, error) {
	token := os.Getenv("ASR_API_TOKEN")
	if token == "" {
		return nil, errors.New("ASR_API_TOKEN is required")
	}

	whisperxEnabled := environmentOrDefaultBool("ASR_ENABLE_WHISPERX", true)
	funasrEnabled := environmentOrDefaultBool("ASR_ENABLE_FUNASR", true)
	funasrRealtimeEnabled := environmentOrDefaultBool("ASR_ENABLE_FUNASR_REALTIME", true)
	whisperxSingleModel := environmentOrDefaultBool("ASR_WHISPERX_SINGLE_MODEL", false)

	if !whisperxEnabled && !funasrEnabled {
		return nil, errors.New("at least one of ASR_ENABLE_WHISPERX or ASR_ENABLE_FUNASR must be true")
	}

	var whisperXURL, whisperXToken string
	if whisperxEnabled {
		whisperXToken = os.Getenv("ASR_WHISPERX_TOKEN")
		if whisperXToken == "" {
			return nil, errors.New("ASR_WHISPERX_TOKEN is required when whisperx is enabled")
		}
		whisperXURL = strings.TrimRight(os.Getenv("ASR_WHISPERX_URL"), "/")
		if whisperXURL == "" {
			return nil, errors.New("ASR_WHISPERX_URL is required when whisperx is enabled")
		}
		if _, err := url.ParseRequestURI(whisperXURL); err != nil {
			return nil, errors.New("ASR_WHISPERX_URL must be a valid URL")
		}
	}

	var funASRURL, funASRToken string
	if funasrEnabled {
		funASRToken = os.Getenv("ASR_FUNASR_TOKEN")
		if funASRToken == "" {
			return nil, errors.New("ASR_FUNASR_TOKEN is required when funasr is enabled")
		}
		funASRURL = strings.TrimRight(os.Getenv("ASR_FUNASR_URL"), "/")
		if funASRURL == "" {
			return nil, errors.New("ASR_FUNASR_URL is required when funasr is enabled")
		}
		if _, err := url.ParseRequestURI(funASRURL); err != nil {
			return nil, errors.New("ASR_FUNASR_URL must be a valid URL")
		}
	}

	upstreams := make(map[string]upstream)
	if whisperxEnabled {
		upstreams["whisperx"] = upstream{
			url:   whisperXURL,
			model: environmentOrDefault("ASR_WHISPERX_MODEL", "large-v3"),
			token: whisperXToken,
		}
	}
	if funasrEnabled {
		upstreams["funasr"] = upstream{
			url:   funASRURL,
			model: environmentOrDefault("ASR_FUNASR_MODEL", "sensevoice"),
			token: funASRToken,
		}
	}

	tm := NewTaskManager(16, upstreams)
	s := &service{
		token:                 token,
		upstreams:             upstreams,
		client:                &http.Client{Timeout: 10 * time.Minute},
		statusClient:          &http.Client{Timeout: 5 * time.Second},
		whisperxEnabled:       whisperxEnabled,
		funasrEnabled:         funasrEnabled,
		funasrRealtimeEnabled: funasrRealtimeEnabled,
		whisperxSingleModel:   whisperxSingleModel,
		taskManager:           tm,
		uploadSem:             make(chan struct{}, environmentOrDefaultInt("ASR_MAX_CONCURRENT_TRANSCRIPTIONS", 2)),
	}
	s.startQueueWorkers(tm)
	return s, nil
}

func environmentOrDefault(name, defaultValue string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return defaultValue
}

func environmentOrDefaultInt(name string, defaultValue int) int {
	if value := os.Getenv(name); value != "" {
		if n, err := strconv.Atoi(value); err == nil && n > 0 {
			return n
		}
	}
	return defaultValue
}

func environmentOrDefaultBool(name string, defaultValue bool) bool {
	value := os.Getenv(name)
	if value == "" {
		return defaultValue
	}
	if b, err := strconv.ParseBool(value); err == nil {
		return b
	}
	return defaultValue
}

func (s *service) getConfig(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"whisperx":              s.whisperxEnabled,
		"funasr":                s.funasrEnabled,
		"funasrrealtime":        s.funasrRealtimeEnabled,
		"whisperx_single_model": s.whisperxSingleModel,
	})
}

func (s *service) health(c *gin.Context) {
	c.Status(http.StatusNoContent)
}

type modelEntry struct {
	ID      string `json:"id"`
	Object  string `json:"object"`
	OwnedBy string `json:"owned_by"`
	Baked   *bool  `json:"baked,omitempty"`
	Loaded  *bool  `json:"loaded,omitempty"`
	Ready   *bool  `json:"ready,omitempty"`
}

func (s *service) models(c *gin.Context) {
	var (
		mutex   sync.Mutex
		wg      sync.WaitGroup
		entries = make([]modelEntry, 0)
	)
	for _, backend := range s.upstreams {
		wg.Add(1)
		go func(backend upstream) {
			defer wg.Done()
			remote, err := s.upstreamModels(c.Request.Context(), backend)
			if err != nil {
				log.Printf("list models from %s: %v", backend.url, err)
				return
			}
			mutex.Lock()
			entries = append(entries, remote...)
			mutex.Unlock()
		}(backend)
	}
	wg.Wait()
	c.JSON(http.StatusOK, gin.H{"object": "list", "data": entries})
}

func (s *service) upstreamModels(parentContext context.Context, backend upstream) ([]modelEntry, error) {
	requestContext, cancel := context.WithTimeout(parentContext, 5*time.Second)
	defer cancel()
	request, err := http.NewRequestWithContext(requestContext, http.MethodGet, backend.url+"/v1/models", nil)
	if err != nil {
		return nil, err
	}
	request.Header.Set("Authorization", "Bearer "+backend.token)
	response, err := s.statusClient.Do(request)
	if err != nil {
		return nil, err
	}
	defer func() {
		if err := response.Body.Close(); err != nil {
			log.Printf("close upstream models response: %v", err)
		}
	}()
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		return nil, fmt.Errorf("upstream returned %d", response.StatusCode)
	}
	var payload struct {
		Data []modelEntry `json:"data"`
	}
	if err := json.NewDecoder(response.Body).Decode(&payload); err != nil {
		return nil, err
	}
	return payload.Data, nil
}

func (s *service) system(c *gin.Context) {
	whisperXStatus := make(chan string, 1)
	funASRStatus := make(chan string, 1)
	go func() {
		if s.whisperxEnabled {
			whisperXStatus <- s.upstreamStatus(c.Request.Context(), s.upstreams["whisperx"])
		} else {
			whisperXStatus <- "disabled"
		}
	}()
	go func() {
		if s.funasrEnabled {
			funASRStatus <- s.upstreamStatus(c.Request.Context(), s.upstreams["funasr"])
		} else {
			funASRStatus <- "disabled"
		}
	}()

	modelsList := make([]gin.H, 0)
	if s.whisperxEnabled {
		modelsList = append(modelsList, gin.H{"id": "whisperx", "upstream_status": <-whisperXStatus})
	} else {
		<-whisperXStatus
	}
	if s.funasrEnabled {
		modelsList = append(modelsList, gin.H{"id": "funasr", "upstream_status": <-funASRStatus})
	} else {
		<-funASRStatus
	}

	c.JSON(http.StatusOK, gin.H{
		"status":             "ok",
		"upload_limit_bytes": maxUploadSize,
		"models":             modelsList,
	})
}

func (s *service) upstreamStatus(parentContext context.Context, backend upstream) string {
	requestContext, cancel := context.WithTimeout(parentContext, 5*time.Second)
	defer cancel()
	request, err := http.NewRequestWithContext(requestContext, http.MethodGet, backend.url+"/health", nil)
	if err != nil {
		log.Printf("build upstream health request: %v", err)
		return "unavailable"
	}
	request.Header.Set("Authorization", "Bearer "+backend.token)
	response, err := s.statusClient.Do(request)
	if err != nil {
		return "unavailable"
	}
	defer func() {
		if err := response.Body.Close(); err != nil {
			log.Printf("close upstream health response: %v", err)
		}
	}()
	if _, err := io.Copy(io.Discard, response.Body); err != nil {
		log.Printf("read upstream health response: %v", err)
		return "unavailable"
	}
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		return "unavailable"
	}
	return "available"
}

func (s *service) authenticate(c *gin.Context) {
	if c.GetHeader("Authorization") != "Bearer "+s.token {
		c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "unauthorized"})
		return
	}
	c.Next()
}

func generateTaskID() string {
	return fmt.Sprintf("task_%d_%06d", time.Now().UnixNano(), rand.Intn(1000000))
}

func (s *service) transcribe(c *gin.Context) {
	select {
	case s.uploadSem <- struct{}{}:
	default:
		c.JSON(http.StatusTooManyRequests, gin.H{"error": "too many concurrent uploads, please retry later"})
		return
	}
	uploadSlotHeld := true
	defer func() {
		if uploadSlotHeld {
			<-s.uploadSem
		}
	}()

	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, maxUploadSize)
	modelName := c.PostForm("model")
	_, ok := s.upstreams[modelName]
	if !ok {
		c.JSON(http.StatusBadRequest, gin.H{"error": fmt.Sprintf("model %s is not supported or not enabled", modelName)})
		return
	}

	level := c.PostForm("level")
	language := c.PostForm("language")
	responseFormat := c.PostForm("response_format")

	file, err := c.FormFile("file")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "audio file is required"})
		return
	}
	input, err := file.Open()
	if err != nil {
		log.Printf("open uploaded audio: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "cannot read uploaded audio"})
		return
	}

	// Create a temp file to store the audio
	tempFile, err := os.CreateTemp("", "asr-upload-*.tmp")
	if err != nil {
		log.Printf("failed to create temp file: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to store uploaded audio"})
		return
	}
	tempPath := tempFile.Name()

	tempFileClosed := false
	defer func() {
		if !tempFileClosed {
			tempFile.Close()
			removeTemporaryFile(tempPath)
		}
	}()

	if _, err := io.Copy(tempFile, input); err != nil {
		log.Printf("failed to write upload to temp file: %v", err)
		if closeErr := input.Close(); closeErr != nil {
			log.Printf("failed to close uploaded audio after copy error: %v", closeErr)
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to store uploaded audio"})
		return
	}
	if err := input.Close(); err != nil {
		log.Printf("failed to close uploaded audio: %v", err)
		removeTemporaryFile(tempPath)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to store uploaded audio"})
		return
	}
	if c.Request.MultipartForm != nil {
		if err := c.Request.MultipartForm.RemoveAll(); err != nil {
			log.Printf("failed to remove multipart temporary files: %v", err)
		}
	}
	if err := tempFile.Close(); err != nil {
		log.Printf("failed to close temporary audio: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to store uploaded audio"})
		return
	}
	tempFileClosed = true

	// Read custom task ID if provided, otherwise generate one
	taskID := c.GetHeader("X-Task-Id")
	if taskID == "" {
		taskID = c.PostForm("task_id")
	}
	if taskID == "" {
		taskID = generateTaskID()
	}

	taskCtx, taskCancel := context.WithCancel(context.Background())

	task := &ASRTask{
		ID:             taskID,
		Status:         StatusPending,
		Model:          modelName,
		Level:          level,
		Language:       language,
		Filename:       file.Filename,
		TempFilePath:   tempPath,
		ResponseFormat: responseFormat,
		ResultChan:     make(chan ASRTaskResult, 1),
		Ctx:            taskCtx,
		CancelFunc:     taskCancel,
		CreatedAt:      time.Now(),
	}

	log.Printf("[ASR API] Adding task %s for file %s to queue", task.ID, task.Filename)
	if err := s.taskManager.Add(task); err != nil {
		taskCancel()
		removeTemporaryFile(tempPath)
		c.JSON(http.StatusTooManyRequests, gin.H{"error": err.Error()})
		return
	}
	<-s.uploadSem
	uploadSlotHeld = false

	c.Header("X-Task-Id", task.ID)

	select {
	case result := <-task.ResultChan:
		if result.Err != nil {
			log.Printf("[ASR API] Task %s failed: %v", task.ID, result.Err)
			if len(result.Body) > 0 {
				c.Header("Content-Type", "application/json")
				c.Status(result.StatusCode)
				if _, err := c.Writer.Write(result.Body); err != nil {
					log.Printf("[ASR API] Failed to write error response for task %s: %v", task.ID, err)
				}
			} else {
				c.JSON(result.StatusCode, gin.H{"error": result.Err.Error()})
			}
			return
		}

		log.Printf("[ASR API] Task %s processed successfully. Status: %d", task.ID, result.StatusCode)
		for k, vv := range result.Header {
			for _, v := range vv {
				c.Header(k, v)
			}
		}
		c.Status(result.StatusCode)
		if _, err := c.Writer.Write(result.Body); err != nil {
			log.Printf("[ASR API] Failed to write response for task %s: %v", task.ID, err)
		}

	case <-c.Request.Context().Done():
		log.Printf("[ASR API] Client disconnected during execution of task %s, triggering cancellation...", task.ID)
		s.taskManager.Cancel(task.ID, s.cancelTaskForModel)
		c.JSON(http.StatusRequestTimeout, gin.H{"error": "client disconnected"})
	}
}

func (s *service) cancelTask(c *gin.Context) {
	id := c.Param("id")
	if id == "" {
		id = c.Query("id")
	}
	if id == "" {
		id = c.PostForm("id")
	}
	if id == "" {
		var body struct {
			ID string `json:"id"`
		}
		if err := c.ShouldBindJSON(&body); err == nil {
			id = body.ID
		}
	}

	if id == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "task id is required"})
		return
	}

	success := s.taskManager.Cancel(id, s.cancelTaskForModel)
	if !success {
		c.JSON(http.StatusNotFound, gin.H{"error": fmt.Sprintf("task %s not found or already completed", id)})
		return
	}

	c.JSON(http.StatusOK, gin.H{"status": "cancelled", "id": id})
}

func (s *service) startQueueWorkers(tm *TaskManager) {
	// WhisperX 与 FunASR 可能部署在不同机器，因此各模型使用独立 worker。
	for model, queue := range tm.queues {
		log.Printf("[Queue] Starting task queue worker for model %s...", model)
		go func(queue *taskQueue) {
			for {
				task := tm.waitForPendingTask(queue)
				log.Printf("[Queue] Worker picked up task %s. Filename: %s", task.ID, task.Filename)

				result := s.processTask(task)
				task.CancelFunc()

				tm.mu.Lock()
				if task.Status == StatusRunning {
					if result.Err != nil {
						task.Status = StatusFailed
						log.Printf("[Queue] Worker finished task %s. Result: Failure (%v)", task.ID, result.Err)
					} else {
						task.Status = StatusCompleted
						log.Printf("[Queue] Worker finished task %s. Result: Success", task.ID)
					}
				} else {
					log.Printf("[Queue] Worker finished task %s. Current status: %s", task.ID, task.Status)
				}
				delete(tm.tasks, task.ID)
				tm.mu.Unlock()

				removeTemporaryFile(task.TempFilePath)

				select {
				case task.ResultChan <- result:
				default:
					log.Printf("[Queue] Task %s result channel is full (handler probably returned already)", task.ID)
				}
			}
		}(queue)
	}
}

func (tm *TaskManager) waitForPendingTask(queue *taskQueue) *ASRTask {
	for {
		tm.mu.Lock()
		if len(queue.pending) > 0 {
			task := queue.pending[0]
			queue.pending[0] = nil
			queue.pending = queue.pending[1:]
			task.Status = StatusRunning
			tm.mu.Unlock()
			return task
		}
		tm.mu.Unlock()
		<-queue.notify
	}
}

func removeTemporaryFile(path string) {
	if path == "" {
		return
	}
	if err := os.Remove(path); err != nil && !errors.Is(err, os.ErrNotExist) {
		log.Printf("remove temporary file %s: %v", path, err)
	}
}

func (s *service) processTask(task *ASRTask) ASRTaskResult {
	if err := task.Ctx.Err(); err != nil {
		return ASRTaskResult{Err: err}
	}

	backend, ok := s.upstreams[task.Model]
	if !ok {
		return ASRTaskResult{
			StatusCode: http.StatusBadRequest,
			Body:       []byte(fmt.Sprintf(`{"error":"model %s is not supported"}`, task.Model)),
			Err:        fmt.Errorf("model %s not supported", task.Model),
		}
	}

	modelForUpstream := backend.model
	if task.Level != "" {
		modelForUpstream = task.Level
	}

	file, err := os.Open(task.TempFilePath)
	if err != nil {
		return ASRTaskResult{
			StatusCode: http.StatusInternalServerError,
			Body:       []byte(`{"error":"failed to open temporary audio file"}`),
			Err:        err,
		}
	}
	defer file.Close()

	body, contentType := buildUpstreamBody(file, task.Filename, modelForUpstream, task.Language, task.ResponseFormat)

	request, err := http.NewRequestWithContext(task.Ctx, http.MethodPost, backend.url+"/v1/audio/transcriptions", body)
	if err != nil {
		return ASRTaskResult{
			StatusCode: http.StatusInternalServerError,
			Body:       []byte(`{"error":"failed to create upstream request"}`),
			Err:        err,
		}
	}
	request.Header.Set("Content-Type", contentType)
	request.Header.Set("Authorization", "Bearer "+backend.token)
	request.Header.Set("X-Task-Id", task.ID)

	log.Printf("[Queue] Sending HTTP post request to %s upstream for task %s", task.Model, task.ID)
	response, err := s.client.Do(request)
	if err != nil {
		return ASRTaskResult{
			StatusCode: http.StatusBadGateway,
			Body:       []byte(`{"error":"model service is unavailable or request was cancelled"}`),
			Err:        err,
		}
	}
	defer response.Body.Close()

	respBody, err := io.ReadAll(response.Body)
	if err != nil {
		return ASRTaskResult{
			StatusCode: http.StatusInternalServerError,
			Body:       []byte(`{"error":"failed to read upstream response"}`),
			Err:        err,
		}
	}

	return ASRTaskResult{
		StatusCode: response.StatusCode,
		Body:       respBody,
		Header:     response.Header,
	}
}

func (s *service) cancelTaskForModel(model, taskID string) {
	if model != "whisperx" && model != "funasr" {
		return
	}
	backend, ok := s.upstreams[model]
	if !ok {
		return
	}
	s.cancelUpstream(backend, taskID)
}

func (s *service) cancelUpstream(backend upstream, taskID string) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, backend.url+"/v1/cancel", nil)
	if err != nil {
		log.Printf("[Queue] Failed to create cancel request for upstream %s: %v", backend.url, err)
		return
	}
	req.Header.Set("Authorization", "Bearer "+backend.token)
	req.Header.Set("X-Task-Id", taskID)
	resp, err := s.statusClient.Do(req)
	if err != nil {
		log.Printf("[Queue] Failed to send cancel request to upstream %s: %v", backend.url, err)
		return
	}
	defer resp.Body.Close()
	log.Printf("[Queue] Sent cancel request to upstream %s, response status: %d", backend.url, resp.StatusCode)
}

func buildUpstreamBody(input io.Reader, filename, model, language, responseFormat string) (io.Reader, string) {
	reader, writer := io.Pipe()
	multipartWriter := multipart.NewWriter(writer)
	go func() {
		if err := writeUpstreamBody(multipartWriter, input, filename, model, language, responseFormat); err != nil {
			if closeErr := writer.CloseWithError(err); closeErr != nil {
				log.Printf("close upstream request body after error: %v", closeErr)
			}
			return
		}
		if err := writer.Close(); err != nil {
			log.Printf("close upstream request body: %v", err)
		}
	}()
	return reader, multipartWriter.FormDataContentType()
}

func writeUpstreamBody(writer *multipart.Writer, input io.Reader, filename, model, language, responseFormat string) error {
	if err := writer.WriteField("model", model); err != nil {
		return err
	}
	if language != "" {
		if err := writer.WriteField("language", language); err != nil {
			return err
		}
	}
	if responseFormat != "" {
		if err := writer.WriteField("response_format", responseFormat); err != nil {
			return err
		}
	}
	part, err := writer.CreateFormFile("file", filename)
	if err != nil {
		return err
	}
	if _, err := io.Copy(part, input); err != nil {
		return err
	}
	return writer.Close()
}
