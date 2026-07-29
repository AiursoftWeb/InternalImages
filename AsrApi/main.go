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

const (
	maxUploadSize         = 100 << 20
	maxCancelTombstones   = 1024
	cancelTombstoneTTL    = 10 * time.Minute
	cancelUpstreamTimeout = 12 * time.Second
)

type upstream struct {
	url   string
	model string
	token string
}

type TaskStatus string

const (
	StatusPending      TaskStatus = "pending"
	StatusRunning      TaskStatus = "running"
	StatusCancelling   TaskStatus = "cancelling"
	StatusCancelFailed TaskStatus = "cancel_failed"
	StatusCompleted    TaskStatus = "completed"
	StatusFailed       TaskStatus = "failed"
	StatusCancelled    TaskStatus = "cancelled"
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

type cancellationRecord struct {
	Model     string
	ExpiresAt time.Time
	Retryable bool
}

type cancellationAttempt struct {
	done chan struct{}
	err  error
}

type TaskManager struct {
	mu                   sync.RWMutex
	tasks                map[string]*ASRTask
	queues               map[string]*taskQueue
	cancelledTaskIDs     map[string]cancellationRecord
	cancellationAttempts map[string]*cancellationAttempt
}

type taskQueue struct {
	pending  []*ASRTask
	capacity int
	notify   chan struct{}
}

func NewTaskManager(queueSize int, models map[string]upstream) *TaskManager {
	manager := &TaskManager{
		tasks:                make(map[string]*ASRTask),
		queues:               make(map[string]*taskQueue, len(models)),
		cancelledTaskIDs:     make(map[string]cancellationRecord),
		cancellationAttempts: make(map[string]*cancellationAttempt),
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
	tm.pruneCancelledTaskIDs(time.Now())
	if _, exists := tm.cancelledTaskIDs[task.ID]; exists {
		return fmt.Errorf("task %s was recently cancelled", task.ID)
	}
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

func (tm *TaskManager) Cancel(id string, cancelUpstreamFunc func(model, taskID string) error) (bool, error) {
	tm.mu.Lock()
	tm.pruneCancelledTaskIDs(time.Now())
	if attempt, exists := tm.cancellationAttempts[id]; exists {
		tm.mu.Unlock()
		return waitForCancellationAttempt(attempt)
	}
	task, ok := tm.tasks[id]
	if !ok {
		record, retryable := tm.cancelledTaskIDs[id]
		if retryable && record.Retryable {
			attempt := tm.startCancellationAttempt(id)
			tm.mu.Unlock()
			return tm.retryCancellation(id, record, attempt, cancelUpstreamFunc)
		}
		tm.mu.Unlock()
		return false, nil
	}
	if task.Status == StatusCompleted || task.Status == StatusFailed || task.Status == StatusCancelled {
		tm.mu.Unlock()
		return false, nil
	}
	prevStatus := task.Status
	if prevStatus == StatusPending {
		task.Status = StatusCancelled
		tm.removePendingTask(task)
		delete(tm.tasks, id)
		tm.recordCancelledTaskID(id, task.Model, false, time.Now())
		if task.CancelFunc != nil {
			task.CancelFunc()
		}
		tm.mu.Unlock()
		log.Printf("[Queue] Task %s is cancelled. Previous status: %s", id, prevStatus)
		publishTaskResult(task, cancelledTaskResult())
		removeTemporaryFile(task.TempFilePath)
		return true, nil
	}

	attempt := tm.startCancellationAttempt(id)
	task.Status = StatusCancelling
	if task.CancelFunc != nil {
		task.CancelFunc()
	}
	tm.mu.Unlock()

	var cancelErr error
	if cancelUpstreamFunc != nil {
		cancelErr = cancelUpstreamFunc(task.Model, task.ID)
	}

	tm.mu.Lock()
	if currentTask := tm.tasks[id]; currentTask == task {
		if cancelErr == nil {
			task.Status = StatusCancelled
		} else {
			task.Status = StatusCancelFailed
		}
		delete(tm.tasks, id)
		tm.recordCancelledTaskID(id, task.Model, cancelErr != nil, time.Now())
	}
	tm.finishCancellationAttempt(id, attempt, cancelErr)
	tm.mu.Unlock()

	if cancelErr != nil {
		log.Printf("[Queue] Failed to confirm cancellation for task %s: %v", id, cancelErr)
		publishTaskResult(task, ASRTaskResult{
			StatusCode: http.StatusBadGateway,
			Body:       []byte(`{"error":"failed to confirm upstream cancellation"}`),
			Err:        cancelErr,
		})
		return true, cancelErr
	}

	log.Printf("[Queue] Task %s is cancelled. Previous status: %s", id, prevStatus)
	publishTaskResult(task, cancelledTaskResult())
	return true, nil
}

func (tm *TaskManager) retryCancellation(id string, record cancellationRecord, attempt *cancellationAttempt, cancelUpstreamFunc func(model, taskID string) error) (bool, error) {
	var cancelErr error
	if cancelUpstreamFunc != nil {
		cancelErr = cancelUpstreamFunc(record.Model, id)
	}

	tm.mu.Lock()
	if currentRecord, exists := tm.cancelledTaskIDs[id]; exists {
		currentRecord.ExpiresAt = time.Now().Add(cancelTombstoneTTL)
		if cancelErr == nil {
			currentRecord.Retryable = false
		}
		tm.cancelledTaskIDs[id] = currentRecord
	}
	tm.finishCancellationAttempt(id, attempt, cancelErr)
	tm.mu.Unlock()

	if cancelErr != nil {
		log.Printf("[Queue] Failed to confirm cancellation retry for task %s: %v", id, cancelErr)
		return true, cancelErr
	}
	log.Printf("[Queue] Upstream cancellation retry succeeded for task %s", id)
	return true, nil
}

func (tm *TaskManager) startCancellationAttempt(id string) *cancellationAttempt {
	attempt := &cancellationAttempt{done: make(chan struct{})}
	tm.cancellationAttempts[id] = attempt
	return attempt
}

func (tm *TaskManager) finishCancellationAttempt(id string, attempt *cancellationAttempt, err error) {
	attempt.err = err
	close(attempt.done)
	delete(tm.cancellationAttempts, id)
}

func waitForCancellationAttempt(attempt *cancellationAttempt) (bool, error) {
	<-attempt.done
	return true, attempt.err
}

func (tm *TaskManager) recordCancellationAttempt(id, model string, retryable bool) {
	tm.mu.Lock()
	defer tm.mu.Unlock()
	tm.recordCancelledTaskID(id, model, retryable, time.Now())
}

func (tm *TaskManager) recordCancelledTaskID(id, model string, retryable bool, now time.Time) {
	tm.pruneCancelledTaskIDs(now)
	if currentRecord, exists := tm.cancelledTaskIDs[id]; exists && !currentRecord.Retryable {
		retryable = false
	}
	tm.cancelledTaskIDs[id] = cancellationRecord{
		Model:     model,
		ExpiresAt: now.Add(cancelTombstoneTTL),
		Retryable: retryable,
	}
	if len(tm.cancelledTaskIDs) > maxCancelTombstones {
		oldestID := id
		oldestExpiry := tm.cancelledTaskIDs[id].ExpiresAt
		for cancelledID, record := range tm.cancelledTaskIDs {
			if record.ExpiresAt.Before(oldestExpiry) {
				oldestID = cancelledID
				oldestExpiry = record.ExpiresAt
			}
		}
		delete(tm.cancelledTaskIDs, oldestID)
	}
}

func (tm *TaskManager) pruneCancelledTaskIDs(now time.Time) {
	for id, record := range tm.cancelledTaskIDs {
		if !record.ExpiresAt.After(now) {
			delete(tm.cancelledTaskIDs, id)
		}
	}
}

func cancelledTaskResult() ASRTaskResult {
	return ASRTaskResult{
		StatusCode: http.StatusBadRequest,
		Body:       []byte(`{"error":"Task was cancelled"}`),
		Err:        errors.New("task was cancelled"),
	}
}

func publishTaskResult(task *ASRTask, result ASRTaskResult) {
	select {
	case task.ResultChan <- result:
	default:
		log.Printf("[Queue] Task %s result channel is full (handler probably returned already)", task.ID)
	}
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
	transcribeSem         chan struct{}
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
		statusClient:          &http.Client{Timeout: cancelUpstreamTimeout},
		whisperxEnabled:       whisperxEnabled,
		funasrEnabled:         funasrEnabled,
		funasrRealtimeEnabled: funasrRealtimeEnabled,
		whisperxSingleModel:   whisperxSingleModel,
		taskManager:           tm,
		uploadSem:             make(chan struct{}, environmentOrDefaultInt("ASR_MAX_CONCURRENT_UPLOADS", 2)),
		transcribeSem:         make(chan struct{}, environmentOrDefaultInt("ASR_MAX_CONCURRENT_TRANSCRIPTIONS", 2)),
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
	defer func() {
		if input == nil {
			return
		}
		if err := input.Close(); err != nil {
			log.Printf("close uploaded audio: %v", err)
		}
	}()

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
			if err := tempFile.Close(); err != nil {
				log.Printf("close temporary audio: %v", err)
			}
			removeTemporaryFile(tempPath)
		}
	}()

	if _, err := io.Copy(tempFile, input); err != nil {
		log.Printf("failed to write upload to temp file: %v", err)
		closeErr := input.Close()
		input = nil
		if closeErr != nil {
			log.Printf("failed to close uploaded audio after copy error: %v", closeErr)
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to store uploaded audio"})
		return
	}
	closeErr := input.Close()
	input = nil
	if closeErr != nil {
		log.Printf("failed to close uploaded audio: %v", closeErr)
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
		if _, err := s.taskManager.Cancel(task.ID, s.cancelTaskForModel); err != nil {
			log.Printf("[ASR API] Failed to confirm cancellation after client disconnected for task %s: %v", task.ID, err)
		}
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

	found, err := s.taskManager.Cancel(id, s.cancelTaskForModel)
	if !found {
		c.JSON(http.StatusNotFound, gin.H{"error": fmt.Sprintf("task %s not found or already completed", id)})
		return
	}
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": "failed to confirm upstream cancellation"})
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

				publishResult := tm.finishTask(task, result)
				removeTemporaryFile(task.TempFilePath)

				if !publishResult {
					continue
				}
				publishTaskResult(task, result)
			}
		}(queue)
	}
}

func (tm *TaskManager) finishTask(task *ASRTask, result ASRTaskResult) bool {
	tm.mu.Lock()
	defer tm.mu.Unlock()
	if task.Status != StatusRunning {
		log.Printf("[Queue] Worker finished task %s. Current status: %s", task.ID, task.Status)
		return false
	}
	if result.Err != nil {
		task.Status = StatusFailed
		log.Printf("[Queue] Worker finished task %s. Result: Failure (%v)", task.ID, result.Err)
	} else {
		task.Status = StatusCompleted
		log.Printf("[Queue] Worker finished task %s. Result: Success", task.ID)
	}
	if currentTask := tm.tasks[task.ID]; currentTask == task {
		delete(tm.tasks, task.ID)
	}
	return true
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
		return cancelledTaskResult()
	}

	if !s.acquireTranscriptionSlot(task.Ctx) {
		return cancelledTaskResult()
	}
	defer s.releaseTranscriptionSlot()

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
		if task.Ctx.Err() == nil {
			s.cancelUpstreamAfterRequestFailure(task, backend)
		}
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

func (s *service) cancelUpstreamAfterRequestFailure(task *ASRTask, backend upstream) {
	cancelErr := s.cancelUpstream(backend, task.ID)
	if s.taskManager != nil {
		s.taskManager.recordCancellationAttempt(task.ID, task.Model, cancelErr != nil)
	}
	if cancelErr != nil {
		log.Printf("[Queue] Failed to stop upstream task %s after transcription request failure: %v", task.ID, cancelErr)
	}
}

func (s *service) acquireTranscriptionSlot(ctx context.Context) bool {
	if s.transcribeSem == nil {
		return true
	}
	select {
	case s.transcribeSem <- struct{}{}:
		return true
	case <-ctx.Done():
		return false
	}
}

func (s *service) releaseTranscriptionSlot() {
	if s.transcribeSem != nil {
		<-s.transcribeSem
	}
}

func (s *service) cancelTaskForModel(model, taskID string) error {
	if model != "whisperx" && model != "funasr" {
		return fmt.Errorf("model %s does not support task cancellation", model)
	}
	backend, ok := s.upstreams[model]
	if !ok {
		return fmt.Errorf("model %s is not configured", model)
	}
	return s.cancelUpstream(backend, taskID)
}

func (s *service) cancelUpstream(backend upstream, taskID string) error {
	ctx, cancel := context.WithTimeout(context.Background(), cancelUpstreamTimeout)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, backend.url+"/v1/cancel", nil)
	if err != nil {
		return fmt.Errorf("create cancel request for upstream %s: %w", backend.url, err)
	}
	req.Header.Set("Authorization", "Bearer "+backend.token)
	req.Header.Set("X-Task-Id", taskID)
	resp, err := s.statusClient.Do(req)
	if err != nil {
		return fmt.Errorf("send cancel request to upstream %s: %w", backend.url, err)
	}
	defer func() {
		if err := resp.Body.Close(); err != nil {
			log.Printf("[Queue] Failed to close cancel response from upstream %s: %v", backend.url, err)
		}
	}()
	if _, err := io.Copy(io.Discard, resp.Body); err != nil {
		return fmt.Errorf("read cancel response from upstream %s: %w", backend.url, err)
	}
	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusAccepted {
		return fmt.Errorf("upstream %s returned cancellation status %d", backend.url, resp.StatusCode)
	}
	log.Printf("[Queue] Upstream %s accepted cancellation for task %s with status %d", backend.url, taskID, resp.StatusCode)
	return nil
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
