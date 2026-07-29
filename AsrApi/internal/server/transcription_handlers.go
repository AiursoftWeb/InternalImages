package server

import (
	"context"
	"errors"
	"fmt"
	"io"
	"log"
	"math/rand"
	"net/http"
	"os"
	"time"

	"github.com/gin-gonic/gin"
)

func generateTaskID() string {
	return fmt.Sprintf("task_%d_%06d", time.Now().UnixNano(), rand.Intn(1000000))
}

func validateTaskID(id string) error {
	if len(id) == 0 {
		return errors.New("task id is required")
	}
	if len(id) > maxTaskIDLength {
		return fmt.Errorf("task id must not exceed %d characters", maxTaskIDLength)
	}
	for _, char := range id {
		if char >= 'a' && char <= 'z' || char >= 'A' && char <= 'Z' || char >= '0' && char <= '9' {
			continue
		}
		if char == '-' || char == '.' || char == '_' || char == '~' {
			continue
		}
		return errors.New("task id must contain only URL-safe ASCII characters")
	}
	return nil
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
	taskID := c.GetHeader("X-Task-Id")
	if taskID != "" {
		if err := validateTaskID(taskID); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
	}
	modelName := c.PostForm("model")
	_, ok := s.upstreams[modelName]
	if !ok {
		c.JSON(http.StatusBadRequest, gin.H{"error": fmt.Sprintf("model %s is not supported or not enabled", modelName)})
		return
	}

	level := c.PostForm("level")
	language := c.PostForm("language")
	responseFormat := c.PostForm("response_format")
	if taskID == "" {
		taskID = c.PostForm("task_id")
	}
	if taskID == "" {
		taskID = generateTaskID()
	}
	if err := validateTaskID(taskID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	file, err := c.FormFile("file")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "audio file is required"})
		return
	}
	task := &ASRTask{
		ID:       taskID,
		Status:   StatusPending,
		Model:    modelName,
		Level:    level,
		Language: language,
		Filename: file.Filename,
	}
	if err := s.taskManager.reserveTaskStorage(task, file.Size); err != nil {
		c.JSON(http.StatusTooManyRequests, gin.H{"error": err.Error()})
		return
	}
	taskStorageHandedOff := false
	defer func() {
		if !taskStorageHandedOff {
			s.taskManager.releaseTaskStorage(task)
		}
	}()
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

	taskCtx, taskCancel := context.WithCancel(context.Background())

	task.TempFilePath = tempPath
	task.ResponseFormat = responseFormat
	task.ResultChan = make(chan ASRTaskResult, 1)
	task.Ctx = taskCtx
	task.CancelFunc = taskCancel
	task.CreatedAt = time.Now()

	log.Printf("[ASR API] Adding task %s for file %s to queue", task.ID, task.Filename)
	if err := s.taskManager.Add(task); err != nil {
		taskCancel()
		removeTemporaryFile(tempPath)
		c.JSON(http.StatusTooManyRequests, gin.H{"error": err.Error()})
		return
	}
	taskStorageHandedOff = true
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
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, maxCancelRequestSize)
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
	if err := validateTaskID(id); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
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
