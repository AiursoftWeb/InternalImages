package server

import (
	"bytes"
	"context"
	"errors"
	"io"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
)

func TestTaskManagerUsesIndependentModelQueues(t *testing.T) {
	models := map[string]upstream{
		"whisperx": {},
		"funasr":   {},
	}
	manager := NewTaskManager(1, maxAudioFileSize, models)

	if err := manager.Add(testTask("whisperx-1", "whisperx", "")); err != nil {
		t.Fatalf("add whisperx task: %v", err)
	}
	if err := manager.Add(testTask("funasr-1", "funasr", "")); err != nil {
		t.Fatalf("add funasr task: %v", err)
	}
	if err := manager.Add(testTask("whisperx-2", "whisperx", "")); err == nil {
		t.Fatal("expected the whisperx queue to be full")
	}
}

func TestTaskManagerLimitsStoredAudioBytes(t *testing.T) {
	manager := NewTaskManager(2, 5, map[string]upstream{"whisperx": {}})
	firstTask := testTask("first", "whisperx", "")
	firstTask.TempFileSize = 3
	if err := manager.Add(firstTask); err != nil {
		t.Fatalf("add first task: %v", err)
	}

	secondTask := testTask("second", "whisperx", "")
	secondTask.TempFileSize = 3
	if err := manager.Add(secondTask); err == nil {
		t.Fatal("expected stored audio capacity to reject second task")
	}

	found, err := manager.Cancel(firstTask.ID, nil)
	if err != nil {
		t.Fatalf("cancel first task: %v", err)
	}
	if !found {
		t.Fatal("expected first task cancellation to succeed")
	}
	if err := manager.Add(secondTask); err != nil {
		t.Fatalf("add second task after releasing storage: %v", err)
	}
}

func TestValidateTaskID(t *testing.T) {
	validTaskIDs := []string{
		"task_123",
		"task.example-123~retry",
		strings.Repeat("a", maxTaskIDLength),
	}
	for _, taskID := range validTaskIDs {
		if err := validateTaskID(taskID); err != nil {
			t.Fatalf("validate task ID %q: %v", taskID, err)
		}
	}

	invalidTaskIDs := []string{
		"",
		"task/id",
		"task id",
		"任务",
		strings.Repeat("a", maxTaskIDLength+1),
	}
	for _, taskID := range invalidTaskIDs {
		if err := validateTaskID(taskID); err == nil {
			t.Fatalf("expected task ID %q to be rejected", taskID)
		}
	}
}

func TestValidateUpstreamURL(t *testing.T) {
	validURLs := []string{
		"http://localhost:8000",
		"https://asr.example.com/base",
	}
	for _, value := range validURLs {
		if err := validateUpstreamURL(value); err != nil {
			t.Fatalf("validate upstream URL %q: %v", value, err)
		}
	}

	invalidURLs := []string{
		"/upstream",
		"ftp://asr.example.com",
		"http:///missing-host",
		"http://asr.example.com?token=value",
	}
	for _, value := range invalidURLs {
		if err := validateUpstreamURL(value); err == nil {
			t.Fatalf("expected upstream URL %q to be rejected", value)
		}
	}
}

func TestEnvironmentOrDefaultIntRejectsInvalidExplicitValue(t *testing.T) {
	invalidValues := []string{"", "0", "-1", "11", "many"}
	for _, value := range invalidValues {
		t.Run(value, func(t *testing.T) {
			t.Setenv("ASR_TEST_POSITIVE_INT", value)
			if _, err := environmentOrDefaultInt("ASR_TEST_POSITIVE_INT", 2, 10); err == nil {
				t.Fatalf("expected integer value %q to be rejected", value)
			} else if !strings.Contains(err.Error(), "ASR_TEST_POSITIVE_INT") {
				t.Fatalf("expected error to name environment variable, got %v", err)
			}
		})
	}
}

func TestEnvironmentOrDefaultIntAcceptsMaximumValue(t *testing.T) {
	t.Setenv("ASR_TEST_POSITIVE_INT", "10")

	value, err := environmentOrDefaultInt("ASR_TEST_POSITIVE_INT", 2, 10)
	if err != nil {
		t.Fatalf("parse maximum integer value: %v", err)
	}
	if value != 10 {
		t.Fatalf("expected maximum value 10, got %d", value)
	}
}

func TestEnvironmentOrDefaultBoolRejectsInvalidExplicitValue(t *testing.T) {
	t.Setenv("ASR_TEST_BOOL", "enabled")

	if _, err := environmentOrDefaultBool("ASR_TEST_BOOL", true); err == nil {
		t.Fatal("expected invalid boolean value to be rejected")
	} else if !strings.Contains(err.Error(), "ASR_TEST_BOOL") {
		t.Fatalf("expected error to name environment variable, got %v", err)
	}
}

func TestModelsReturnsBadGatewayWhenAnyUpstreamFails(t *testing.T) {
	gin.SetMode(gin.TestMode)
	availableUpstream := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		writer.Header().Set("Content-Type", "application/json")
		if _, err := writer.Write([]byte(`{"data":[{"id":"large-v3"}]}`)); err != nil {
			t.Errorf("write available upstream response: %v", err)
		}
	}))
	defer availableUpstream.Close()
	failedUpstream := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		http.Error(writer, "unavailable", http.StatusServiceUnavailable)
	}))
	defer failedUpstream.Close()

	server := &service{
		upstreams: map[string]upstream{
			"whisperx": {url: availableUpstream.URL},
			"funasr":   {url: failedUpstream.URL},
		},
		statusClient: &http.Client{Timeout: time.Second},
	}
	request := httptest.NewRequest(http.MethodGet, "/v1/models", nil)
	recorder := httptest.NewRecorder()
	context, _ := gin.CreateTestContext(recorder)
	context.Request = request

	server.models(context)

	if recorder.Code != http.StatusBadGateway {
		t.Fatalf("expected status %d, got %d", http.StatusBadGateway, recorder.Code)
	}
	if !strings.Contains(recorder.Body.String(), "failed to list models from upstream services") {
		t.Fatalf("unexpected models error response %q", recorder.Body.String())
	}
}

func TestTranscribeRejectsInvalidHeaderTaskIDBeforeReadingBody(t *testing.T) {
	gin.SetMode(gin.TestMode)
	server := &service{uploadSem: make(chan struct{}, 1)}
	body := &trackingReadCloser{}
	request := httptest.NewRequest(http.MethodPost, "/v1/audio/transcriptions", body)
	request.Header.Set("X-Task-Id", "invalid/task")
	recorder := httptest.NewRecorder()
	context, _ := gin.CreateTestContext(recorder)
	context.Request = request

	server.transcribe(context)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected status %d, got %d", http.StatusBadRequest, recorder.Code)
	}
	if body.reads != 0 {
		t.Fatalf("expected invalid task ID request body not to be read, got %d reads", body.reads)
	}
}

func TestCancelTaskLimitsRequestBody(t *testing.T) {
	gin.SetMode(gin.TestMode)
	bodyContent := `{"id":"` + strings.Repeat("a", maxCancelRequestSize*2) + `"}`
	body := &countingReadCloser{reader: strings.NewReader(bodyContent)}
	request := httptest.NewRequest(http.MethodPost, "/v1/tasks/cancel", body)
	request.Header.Set("Content-Type", "application/json")
	recorder := httptest.NewRecorder()
	context, _ := gin.CreateTestContext(recorder)
	context.Request = request

	(&service{}).cancelTask(context)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected status %d, got %d", http.StatusBadRequest, recorder.Code)
	}
	if body.bytesRead > maxCancelRequestSize+1 {
		t.Fatalf("expected at most %d body bytes to be read, got %d", maxCancelRequestSize+1, body.bytesRead)
	}
	if body.bytesRead >= len(bodyContent) {
		t.Fatal("expected oversized cancellation body not to be read completely")
	}
}

func TestCancelPendingTaskReleasesQueueCapacityAndRemovesFile(t *testing.T) {
	models := map[string]upstream{"whisperx": {}}
	manager := NewTaskManager(1, maxAudioFileSize, models)
	audioPath := writeTestAudio(t, "cancelled.wav")
	cancelledTask := testTask("cancelled", "whisperx", audioPath)
	if err := manager.Add(cancelledTask); err != nil {
		t.Fatalf("add task to cancel: %v", err)
	}

	found, err := manager.Cancel(cancelledTask.ID, nil)
	if err != nil {
		t.Fatalf("cancel pending task: %v", err)
	}
	if !found {
		t.Fatal("expected pending task cancellation to succeed")
	}
	if _, err := os.Stat(audioPath); !os.IsNotExist(err) {
		t.Fatalf("expected cancelled task file to be removed, got: %v", err)
	}
	if err := manager.Add(testTask("replacement", "whisperx", "")); err != nil {
		t.Fatalf("expected cancelled task to release queue capacity: %v", err)
	}
}

func TestCancelRunningTaskPassesTaskIDToUpstream(t *testing.T) {
	models := map[string]upstream{"whisperx": {}}
	manager := NewTaskManager(1, maxAudioFileSize, models)
	task := testTask("running-task", "whisperx", "")
	if err := manager.Add(task); err != nil {
		t.Fatalf("add running task: %v", err)
	}
	manager.waitForPendingTask(manager.queues["whisperx"])

	var cancelledModel string
	var cancelledTaskID string
	found, err := manager.Cancel(task.ID, func(model, taskID string) error {
		cancelledModel = model
		cancelledTaskID = taskID
		return nil
	})
	if err != nil {
		t.Fatalf("cancel running task: %v", err)
	}
	if !found {
		t.Fatal("expected running task cancellation to succeed")
	}
	if cancelledModel != task.Model {
		t.Fatalf("expected cancelled model %q, got %q", task.Model, cancelledModel)
	}
	if cancelledTaskID != task.ID {
		t.Fatalf("expected cancelled task ID %q, got %q", task.ID, cancelledTaskID)
	}
}

func TestCancelRunningTaskWaitsForUpstreamConfirmationBeforePublishingResult(t *testing.T) {
	manager := NewTaskManager(1, maxAudioFileSize, map[string]upstream{"whisperx": {}})
	task := testTask("running-task", "whisperx", "")
	if err := manager.Add(task); err != nil {
		t.Fatalf("add running task: %v", err)
	}
	manager.waitForPendingTask(manager.queues["whisperx"])

	cancelStarted := make(chan struct{})
	releaseCancel := make(chan struct{})
	cancelled := make(chan struct {
		found bool
		err   error
	}, 1)
	go func() {
		found, err := manager.Cancel(task.ID, func(_, _ string) error {
			close(cancelStarted)
			<-releaseCancel
			return nil
		})
		cancelled <- struct {
			found bool
			err   error
		}{found: found, err: err}
	}()

	select {
	case <-cancelStarted:
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for upstream cancellation")
	}

	select {
	case result := <-task.ResultChan:
		t.Fatalf("received cancellation result before upstream confirmation: %+v", result)
	case <-time.After(100 * time.Millisecond):
	}

	if err := manager.Add(testTask(task.ID, "whisperx", "")); err == nil {
		t.Fatal("expected task ID to remain reserved during upstream cancellation")
	}
	close(releaseCancel)
	cancelResult := <-cancelled
	if cancelResult.err != nil {
		t.Fatalf("cancel running task: %v", cancelResult.err)
	}
	if !cancelResult.found {
		t.Fatal("expected running task cancellation to succeed")
	}
	select {
	case result := <-task.ResultChan:
		if result.StatusCode != http.StatusBadRequest {
			t.Fatalf("expected cancellation status %d, got %d", http.StatusBadRequest, result.StatusCode)
		}
		if result.Err == nil {
			t.Fatal("expected cancellation result to contain an error")
		}
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for confirmed cancellation result")
	}
}

func TestConcurrentCancellationSharesUpstreamResult(t *testing.T) {
	manager := NewTaskManager(1, maxAudioFileSize, map[string]upstream{"whisperx": {}})
	task := testTask("running-task", "whisperx", "")
	if err := manager.Add(task); err != nil {
		t.Fatalf("add running task: %v", err)
	}
	manager.waitForPendingTask(manager.queues["whisperx"])

	cancelCalls := make(chan struct{}, 2)
	releaseCancel := make(chan struct{})
	var releaseOnce sync.Once
	t.Cleanup(func() {
		releaseOnce.Do(func() {
			close(releaseCancel)
		})
	})
	upstreamErr := errors.New("upstream unavailable")
	cancelUpstream := func(_, _ string) error {
		cancelCalls <- struct{}{}
		<-releaseCancel
		return upstreamErr
	}
	results := make(chan struct {
		found bool
		err   error
	}, 2)
	cancel := func() {
		found, err := manager.Cancel(task.ID, cancelUpstream)
		results <- struct {
			found bool
			err   error
		}{found: found, err: err}
	}

	go cancel()
	select {
	case <-cancelCalls:
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for upstream cancellation")
	}
	go cancel()

	select {
	case <-cancelCalls:
		t.Fatal("expected concurrent cancellation to share the upstream request")
	case result := <-results:
		t.Fatalf("concurrent cancellation returned before upstream result: %+v", result)
	case <-time.After(100 * time.Millisecond):
	}

	releaseOnce.Do(func() {
		close(releaseCancel)
	})
	for range 2 {
		result := <-results
		if !result.found {
			t.Fatal("expected both cancellation calls to find the running task")
		}
		if !errors.Is(result.err, upstreamErr) {
			t.Fatalf("expected shared upstream error, got %v", result.err)
		}
	}
	select {
	case <-cancelCalls:
		t.Fatal("expected exactly one upstream cancellation call")
	default:
	}
}

func TestCancelRunningTaskRemovesTaskWhenUpstreamCancellationFails(t *testing.T) {
	manager := NewTaskManager(1, maxAudioFileSize, map[string]upstream{"whisperx": {}})
	task := testTask("running-task", "whisperx", "")
	if err := manager.Add(task); err != nil {
		t.Fatalf("add running task: %v", err)
	}
	manager.waitForPendingTask(manager.queues["whisperx"])

	upstreamErr := errors.New("upstream unavailable")
	found, err := manager.Cancel(task.ID, func(_, _ string) error {
		return upstreamErr
	})
	if !found {
		t.Fatal("expected running task to be found")
	}
	if !errors.Is(err, upstreamErr) {
		t.Fatalf("expected upstream cancellation error, got %v", err)
	}

	manager.mu.RLock()
	_, exists := manager.tasks[task.ID]
	manager.mu.RUnlock()
	if exists {
		t.Fatal("expected task to be removed after cancellation failure")
	}
	if task.Status != StatusCancelFailed {
		t.Fatalf("expected status %q, got %q", StatusCancelFailed, task.Status)
	}

	result := <-task.ResultChan
	if result.StatusCode != http.StatusBadGateway {
		t.Fatalf("expected status %d, got %d", http.StatusBadGateway, result.StatusCode)
	}
	if err := manager.Add(testTask(task.ID, "whisperx", "")); err == nil {
		t.Fatal("expected failed cancellation task ID reuse to be rejected")
	}

	retryCalls := 0
	retryErr := errors.New("upstream still unavailable")
	found, err = manager.Cancel(task.ID, func(model, taskID string) error {
		retryCalls++
		if model != task.Model {
			t.Fatalf("expected retry model %q, got %q", task.Model, model)
		}
		if taskID != task.ID {
			t.Fatalf("expected retry task ID %q, got %q", task.ID, taskID)
		}
		return retryErr
	})
	if !errors.Is(err, retryErr) {
		t.Fatalf("expected retry error, got %v", err)
	}
	if !found {
		t.Fatal("expected failed cancellation to be retryable")
	}
	if retryCalls != 1 {
		t.Fatalf("expected one retry call, got %d", retryCalls)
	}

	found, err = manager.Cancel(task.ID, func(_, _ string) error {
		retryCalls++
		return nil
	})
	if err != nil {
		t.Fatalf("retry cancellation after repeated failure: %v", err)
	}
	if !found {
		t.Fatal("expected repeated cancellation failure to remain retryable")
	}
	if retryCalls != 2 {
		t.Fatalf("expected two retry calls, got %d", retryCalls)
	}

	found, err = manager.Cancel(task.ID, func(_, _ string) error {
		retryCalls++
		return nil
	})
	if err != nil {
		t.Fatalf("cancel confirmed task: %v", err)
	}
	if found {
		t.Fatal("expected confirmed cancellation not to be retryable")
	}
	if retryCalls != 2 {
		t.Fatalf("expected confirmed cancellation not to call upstream, got %d calls", retryCalls)
	}
}

func TestCancelledTaskIDCannotBeReusedDuringTombstoneTTL(t *testing.T) {
	manager := NewTaskManager(1, maxAudioFileSize, map[string]upstream{"whisperx": {}})
	cancelledTask := testTask("reused-task", "whisperx", "")
	if err := manager.Add(cancelledTask); err != nil {
		t.Fatalf("add cancelled task: %v", err)
	}
	manager.waitForPendingTask(manager.queues["whisperx"])
	found, err := manager.Cancel(cancelledTask.ID, nil)
	if err != nil {
		t.Fatalf("cancel running task: %v", err)
	}
	if !found {
		t.Fatal("expected running task cancellation to succeed")
	}

	replacementTask := testTask(cancelledTask.ID, "whisperx", "")
	if err := manager.Add(replacementTask); err == nil {
		t.Fatal("expected cancelled task ID reuse to be rejected")
	}
	if manager.finishTask(cancelledTask, ASRTaskResult{StatusCode: http.StatusOK}) {
		t.Fatal("expected cancelled worker result not to be published")
	}
}

func TestCancelledTaskIDCanBeReusedAfterTombstoneExpires(t *testing.T) {
	manager := NewTaskManager(1, maxAudioFileSize, map[string]upstream{"whisperx": {}})
	task := testTask("reusable-task", "whisperx", "")
	if err := manager.Add(task); err != nil {
		t.Fatalf("add task: %v", err)
	}
	found, err := manager.Cancel(task.ID, nil)
	if err != nil {
		t.Fatalf("cancel pending task: %v", err)
	}
	if !found {
		t.Fatal("expected pending task cancellation to succeed")
	}

	manager.mu.Lock()
	manager.cancelledTaskIDs[task.ID] = cancellationRecord{
		ExpiresAt: time.Now().Add(-time.Second),
	}
	manager.mu.Unlock()

	if err := manager.Add(testTask(task.ID, "whisperx", "")); err != nil {
		t.Fatalf("reuse task ID after tombstone expiry: %v", err)
	}
}

func TestCancelUnknownTaskDoesNotCallUpstream(t *testing.T) {
	manager := NewTaskManager(1, maxAudioFileSize, map[string]upstream{"whisperx": {}})
	cancelCalled := false

	found, err := manager.Cancel("unknown-task", func(_, _ string) error {
		cancelCalled = true
		return nil
	})
	if err != nil {
		t.Fatalf("cancel unknown task: %v", err)
	}
	if found {
		t.Fatal("expected unknown task cancellation to fail")
	}
	if cancelCalled {
		t.Fatal("expected unknown task not to reach upstream cancellation")
	}
}

func TestTranscribeRejectsUploadBeforeReadingBodyWhenAdmissionIsFull(t *testing.T) {
	gin.SetMode(gin.TestMode)
	server := &service{uploadSem: make(chan struct{}, 1)}
	server.uploadSem <- struct{}{}
	body := &trackingReadCloser{}
	request := httptest.NewRequest(http.MethodPost, "/v1/audio/transcriptions", body)
	recorder := httptest.NewRecorder()
	context, _ := gin.CreateTestContext(recorder)
	context.Request = request

	server.transcribe(context)

	if recorder.Code != http.StatusTooManyRequests {
		t.Fatalf("expected status %d, got %d", http.StatusTooManyRequests, recorder.Code)
	}
	if body.reads != 0 {
		t.Fatalf("expected rejected upload body not to be read, got %d reads", body.reads)
	}
}

func TestReadTranscriptionUploadStreamsIntoReservedStorage(t *testing.T) {
	manager := NewTaskManager(1, 5, map[string]upstream{"whisperx": {}})
	server := &service{taskManager: manager}
	task := &ASRTask{}
	request := newMultipartTranscriptionRequest(t, "audio", map[string]string{
		"model":           "whisperx",
		"level":           "large-v3",
		"language":        "en",
		"response_format": "json",
		"task_id":         "streamed-task",
	})

	upload, err := server.readTranscriptionUpload(request, task)
	if err != nil {
		t.Fatalf("read transcription upload: %v", err)
	}
	t.Cleanup(func() {
		removeTemporaryFile(upload.TempFilePath)
		manager.releaseTaskStorage(task)
	})

	if request.MultipartForm == nil || len(request.MultipartForm.File) != 0 {
		t.Fatal("expected MultipartReader to avoid buffering uploaded files")
	}
	if task.TempFileSize != 5 {
		t.Fatalf("expected 5 reserved bytes, got %d", task.TempFileSize)
	}
	if upload.Model != "whisperx" || upload.Level != "large-v3" || upload.Language != "en" {
		t.Fatalf("unexpected upload fields: %+v", upload)
	}
	if upload.ResponseFormat != "json" || upload.TaskID != "streamed-task" {
		t.Fatalf("unexpected upload metadata: %+v", upload)
	}
	content, err := os.ReadFile(upload.TempFilePath)
	if err != nil {
		t.Fatalf("read stored audio: %v", err)
	}
	if string(content) != "audio" {
		t.Fatalf("expected stored audio %q, got %q", "audio", content)
	}
}

func TestReadTranscriptionUploadEnforcesStorageLimitWhileStreaming(t *testing.T) {
	manager := NewTaskManager(1, 4, map[string]upstream{"whisperx": {}})
	server := &service{taskManager: manager}
	task := &ASRTask{}
	request := newMultipartTranscriptionRequest(t, "audio", map[string]string{"model": "whisperx"})

	if _, err := server.readTranscriptionUpload(request, task); !errors.Is(err, errStoredAudioCapacity) {
		t.Fatalf("expected stored audio capacity error, got %v", err)
	}
	manager.releaseTaskStorage(task)
	if manager.storedBytes != 0 {
		t.Fatalf("expected rejected upload reservation to be released, got %d bytes", manager.storedBytes)
	}
}

func TestTranscriptionUploadErrorResponseReturnsRequestEntityTooLarge(t *testing.T) {
	manager := NewTaskManager(1, maxAudioFileSize, map[string]upstream{"whisperx": {}})
	server := &service{taskManager: manager}
	task := &ASRTask{}
	request := newMultipartTranscriptionRequest(t, "audio", map[string]string{"model": "whisperx"})
	request.Body = http.MaxBytesReader(httptest.NewRecorder(), request.Body, 4)

	_, err := server.readTranscriptionUpload(request, task)
	manager.releaseTaskStorage(task)
	statusCode, message := transcriptionUploadErrorResponse(err)

	if statusCode != http.StatusRequestEntityTooLarge {
		t.Fatalf("expected status %d, got %d", http.StatusRequestEntityTooLarge, statusCode)
	}
	if message != "audio file exceeds 100 MiB limit" {
		t.Fatalf("unexpected oversized upload message %q", message)
	}
}

func TestCopyAudioAllowsExactFileSizeLimit(t *testing.T) {
	manager := NewTaskManager(1, maxAudioFileSize, map[string]upstream{"whisperx": {}})
	manager.storedBytes = maxAudioFileSize - 1
	task := &ASRTask{
		TempFileSize:    maxAudioFileSize - 1,
		storageReserved: true,
	}
	server := &service{taskManager: manager}

	if err := server.copyAudioWithStorageReservation(io.Discard, strings.NewReader("a"), task); err != nil {
		t.Fatalf("copy audio at exact file size limit: %v", err)
	}
	if task.TempFileSize != maxAudioFileSize {
		t.Fatalf("expected stored size %d, got %d", maxAudioFileSize, task.TempFileSize)
	}
	manager.releaseTaskStorage(task)
}

func TestCopyAudioRejectsFileLargerThanLimit(t *testing.T) {
	manager := NewTaskManager(1, maxAudioFileSize, map[string]upstream{"whisperx": {}})
	manager.storedBytes = maxAudioFileSize - 1
	task := &ASRTask{
		TempFileSize:    maxAudioFileSize - 1,
		storageReserved: true,
	}
	server := &service{taskManager: manager}

	err := server.copyAudioWithStorageReservation(io.Discard, strings.NewReader("ab"), task)
	var maxBytesError *http.MaxBytesError
	if !errors.As(err, &maxBytesError) {
		t.Fatalf("expected audio file size error, got %v", err)
	}
	if maxBytesError.Limit != maxAudioFileSize {
		t.Fatalf("expected audio limit %d, got %d", maxAudioFileSize, maxBytesError.Limit)
	}
	manager.releaseTaskStorage(task)
}

func TestQueueWorkersProcessDifferentModelsConcurrently(t *testing.T) {
	started := make(chan string, 2)
	release := make(chan struct{})
	var releaseOnce sync.Once
	t.Cleanup(func() {
		releaseOnce.Do(func() {
			close(release)
		})
	})
	newUpstream := func(model string) *httptest.Server {
		return httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
			started <- model
			<-release
			writer.Header().Set("Content-Type", "application/json")
			if _, err := writer.Write([]byte(`{"text":"ok"}`)); err != nil {
				t.Errorf("write %s response: %v", model, err)
			}
		}))
	}

	whisperxServer := newUpstream("whisperx")
	defer whisperxServer.Close()
	funasrServer := newUpstream("funasr")
	defer funasrServer.Close()

	models := map[string]upstream{
		"whisperx": {url: whisperxServer.URL, model: "large-v3", token: "token"},
		"funasr":   {url: funasrServer.URL, model: "sensevoice", token: "token"},
	}
	manager := NewTaskManager(1, maxAudioFileSize, models)
	server := &service{
		upstreams:     models,
		client:        &http.Client{Timeout: time.Second},
		taskManager:   manager,
		transcribeSem: make(chan struct{}, 2),
	}
	server.startQueueWorkers(manager)

	whisperxPath := writeTestAudio(t, "whisperx.wav")
	funasrPath := writeTestAudio(t, "funasr.wav")
	whisperxTask := testTask("whisperx-task", "whisperx", whisperxPath)
	funasrTask := testTask("funasr-task", "funasr", funasrPath)
	if err := manager.Add(whisperxTask); err != nil {
		t.Fatalf("add whisperx task: %v", err)
	}
	if err := manager.Add(funasrTask); err != nil {
		t.Fatalf("add funasr task: %v", err)
	}

	first := waitForStartedModel(t, started)
	second := waitForStartedModel(t, started)
	if first == second {
		t.Fatalf("expected both model workers to start, got %q twice", first)
	}
	releaseOnce.Do(func() {
		close(release)
	})

	waitForTaskResult(t, whisperxTask)
	waitForTaskResult(t, funasrTask)
}

func TestQueueWorkerProcessesSameModelSerially(t *testing.T) {
	started := make(chan string, 2)
	release := make(chan struct{})
	var releaseOnce sync.Once
	t.Cleanup(func() {
		releaseOnce.Do(func() {
			close(release)
		})
	})
	upstreamServer := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		started <- request.Header.Get("X-Task-Id")
		<-release
		writer.Header().Set("Content-Type", "application/json")
		if _, err := writer.Write([]byte(`{"text":"ok"}`)); err != nil {
			t.Errorf("write response: %v", err)
		}
	}))
	defer upstreamServer.Close()

	models := map[string]upstream{
		"whisperx": {url: upstreamServer.URL, model: "large-v3", token: "token"},
	}
	manager := NewTaskManager(2, maxAudioFileSize, models)
	server := &service{
		upstreams:     models,
		client:        &http.Client{Timeout: time.Second},
		taskManager:   manager,
		transcribeSem: make(chan struct{}, 2),
	}
	server.startQueueWorkers(manager)

	firstTask := testTask("whisperx-first", "whisperx", writeTestAudio(t, "first.wav"))
	secondTask := testTask("whisperx-second", "whisperx", writeTestAudio(t, "second.wav"))
	if err := manager.Add(firstTask); err != nil {
		t.Fatalf("add first whisperx task: %v", err)
	}
	if err := manager.Add(secondTask); err != nil {
		t.Fatalf("add second whisperx task: %v", err)
	}

	firstStarted := waitForStartedModel(t, started)
	if firstStarted != firstTask.ID {
		t.Fatalf("expected first task %q to start, got %q", firstTask.ID, firstStarted)
	}
	select {
	case taskID := <-started:
		t.Fatalf("expected same-model task to remain queued, but %s started", taskID)
	case <-time.After(100 * time.Millisecond):
	}

	releaseOnce.Do(func() {
		close(release)
	})
	secondStarted := waitForStartedModel(t, started)
	if secondStarted != secondTask.ID {
		t.Fatalf("expected second task %q to start, got %q", secondTask.ID, secondStarted)
	}
	waitForTaskResult(t, firstTask)
	waitForTaskResult(t, secondTask)
}

func TestQueueWorkersRespectGlobalTranscriptionLimit(t *testing.T) {
	started := make(chan string, 2)
	release := make(chan struct{})
	var releaseOnce sync.Once
	t.Cleanup(func() {
		releaseOnce.Do(func() {
			close(release)
		})
	})
	newUpstream := func(model string) *httptest.Server {
		return httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
			started <- model
			<-release
			writer.Header().Set("Content-Type", "application/json")
			if _, err := writer.Write([]byte(`{"text":"ok"}`)); err != nil {
				t.Errorf("write %s response: %v", model, err)
			}
		}))
	}

	whisperxServer := newUpstream("whisperx")
	defer whisperxServer.Close()
	funasrServer := newUpstream("funasr")
	defer funasrServer.Close()
	models := map[string]upstream{
		"whisperx": {url: whisperxServer.URL, model: "large-v3", token: "token"},
		"funasr":   {url: funasrServer.URL, model: "sensevoice", token: "token"},
	}
	manager := NewTaskManager(1, maxAudioFileSize, models)
	server := &service{
		upstreams:     models,
		client:        &http.Client{Timeout: time.Second},
		taskManager:   manager,
		transcribeSem: make(chan struct{}, 1),
	}
	server.startQueueWorkers(manager)

	whisperxTask := testTask("whisperx-task", "whisperx", writeTestAudio(t, "whisperx.wav"))
	funasrTask := testTask("funasr-task", "funasr", writeTestAudio(t, "funasr.wav"))
	if err := manager.Add(whisperxTask); err != nil {
		t.Fatalf("add whisperx task: %v", err)
	}
	if err := manager.Add(funasrTask); err != nil {
		t.Fatalf("add funasr task: %v", err)
	}

	waitForStartedModel(t, started)
	select {
	case model := <-started:
		t.Fatalf("expected global transcription limit to block %s", model)
	case <-time.After(100 * time.Millisecond):
	}

	releaseOnce.Do(func() {
		close(release)
	})
	waitForStartedModel(t, started)
	waitForTaskResult(t, whisperxTask)
	waitForTaskResult(t, funasrTask)
}

func TestProcessTaskPassesTaskIDToUpstream(t *testing.T) {
	const taskID = "bound-task"
	upstreamServer := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if actual := request.Header.Get("X-Task-Id"); actual != taskID {
			t.Errorf("expected task ID %q, got %q", taskID, actual)
		}
		writer.Header().Set("Content-Type", "application/json")
		if _, err := writer.Write([]byte(`{"text":"ok"}`)); err != nil {
			t.Errorf("write response: %v", err)
		}
	}))
	defer upstreamServer.Close()

	audioPath := writeTestAudio(t, "bound.wav")
	server := &service{
		upstreams: map[string]upstream{
			"whisperx": {url: upstreamServer.URL, model: "large-v3", token: "token"},
		},
		client: &http.Client{Timeout: time.Second},
	}

	result := server.processTask(testTask(taskID, "whisperx", audioPath))
	if result.Err != nil {
		t.Fatalf("process task: %v", result.Err)
	}
}

func TestFinishTaskMarksNonSuccessfulUpstreamStatusAsFailed(t *testing.T) {
	testCases := []struct {
		name       string
		taskID     string
		statusCode int
	}{
		{name: "redirect", taskID: "upstream-redirect", statusCode: http.StatusNotModified},
		{name: "server error", taskID: "upstream-error", statusCode: http.StatusServiceUnavailable},
	}

	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			manager := NewTaskManager(1, maxAudioFileSize, map[string]upstream{"whisperx": {}})
			task := testTask(testCase.taskID, "whisperx", "")
			if err := manager.Add(task); err != nil {
				t.Fatalf("add unsuccessful upstream task: %v", err)
			}
			manager.waitForPendingTask(manager.queues["whisperx"])
			result := ASRTaskResult{
				StatusCode: testCase.statusCode,
				Body:       []byte(`{"error":"upstream request failed"}`),
				Header:     http.Header{"Content-Type": []string{"application/json"}},
			}

			if !manager.finishTask(task, result) {
				t.Fatal("expected unsuccessful upstream result to be published")
			}
			if task.Status != StatusFailed {
				t.Fatalf("expected task status %q, got %q", StatusFailed, task.Status)
			}
			if result.Err != nil {
				t.Fatalf("expected upstream response to remain transferable, got %v", result.Err)
			}
		})
	}
}

func TestProcessTaskCancelsUpstreamAfterTransportFailure(t *testing.T) {
	const taskID = "transport-failure"
	cancelledTaskID := make(chan string, 1)
	upstreamServer := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.URL.Path == "/v1/cancel" {
			cancelledTaskID <- request.Header.Get("X-Task-Id")
			writer.WriteHeader(http.StatusAccepted)
			return
		}
		panic(http.ErrAbortHandler)
	}))
	defer upstreamServer.Close()

	models := map[string]upstream{
		"whisperx": {url: upstreamServer.URL, model: "large-v3", token: "token"},
	}
	manager := NewTaskManager(1, maxAudioFileSize, models)
	server := &service{
		upstreams:    models,
		client:       &http.Client{Timeout: time.Second},
		statusClient: &http.Client{Timeout: time.Second},
		taskManager:  manager,
	}
	task := testTask(taskID, "whisperx", writeTestAudio(t, "failed.wav"))

	result := server.processTask(task)
	if result.Err == nil {
		t.Fatal("expected transcription transport failure")
	}
	select {
	case actualTaskID := <-cancelledTaskID:
		if actualTaskID != taskID {
			t.Fatalf("expected cancelled task ID %q, got %q", taskID, actualTaskID)
		}
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for upstream cancellation")
	}
}

func TestTransportFailureAndExternalCancellationShareUpstreamRequest(t *testing.T) {
	const taskID = "shared-transport-failure"
	cancelRequests := make(chan struct{}, 2)
	releaseCancel := make(chan struct{})
	var releaseOnce sync.Once
	t.Cleanup(func() {
		releaseOnce.Do(func() {
			close(releaseCancel)
		})
	})
	upstreamServer := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.URL.Path == "/v1/cancel" {
			cancelRequests <- struct{}{}
			<-releaseCancel
			writer.WriteHeader(http.StatusAccepted)
			return
		}
		panic(http.ErrAbortHandler)
	}))
	defer upstreamServer.Close()

	models := map[string]upstream{
		"whisperx": {url: upstreamServer.URL, model: "large-v3", token: "token"},
	}
	manager := NewTaskManager(1, maxAudioFileSize, models)
	server := &service{
		upstreams:    models,
		client:       &http.Client{Timeout: time.Second},
		statusClient: &http.Client{Timeout: time.Second},
		taskManager:  manager,
	}
	task := testTask(taskID, "whisperx", writeTestAudio(t, "shared-failure.wav"))
	if err := manager.Add(task); err != nil {
		t.Fatalf("add task: %v", err)
	}
	manager.waitForPendingTask(manager.queues["whisperx"])

	processResult := make(chan ASRTaskResult, 1)
	go func() {
		processResult <- server.processTask(task)
	}()
	select {
	case <-cancelRequests:
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for compensating cancellation")
	}

	cancelResult := make(chan struct {
		found bool
		err   error
	}, 1)
	go func() {
		found, err := manager.Cancel(task.ID, server.cancelTaskForModel)
		cancelResult <- struct {
			found bool
			err   error
		}{found: found, err: err}
	}()

	select {
	case <-cancelRequests:
		t.Fatal("expected external cancellation to share the compensating request")
	case result := <-cancelResult:
		t.Fatalf("external cancellation returned before the shared request: %+v", result)
	case <-time.After(100 * time.Millisecond):
	}

	releaseOnce.Do(func() {
		close(releaseCancel)
	})
	result := <-processResult
	if result.Err == nil {
		t.Fatal("expected transcription transport failure")
	}
	cancelled := <-cancelResult
	if !cancelled.found {
		t.Fatal("expected external cancellation to find the active attempt")
	}
	if cancelled.err != nil {
		t.Fatalf("external cancellation: %v", cancelled.err)
	}
	found, err := manager.Cancel(task.ID, server.cancelTaskForModel)
	if err != nil {
		t.Fatalf("cancel task after compensating cancellation: %v", err)
	}
	if found {
		t.Fatal("expected confirmed compensating cancellation not to call upstream again")
	}
	select {
	case <-cancelRequests:
		t.Fatal("expected exactly one upstream cancellation request")
	default:
	}
	if !manager.finishTask(task, result) {
		t.Fatal("expected failed task to finish after compensating cancellation")
	}
	manager.releaseTaskStorage(task)
}

func TestCancelUpstreamPassesTaskID(t *testing.T) {
	const taskID = "cancelled-task"
	requestReceived := make(chan struct{}, 1)
	upstreamServer := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if actual := request.Header.Get("X-Task-Id"); actual != taskID {
			t.Errorf("expected task ID %q, got %q", taskID, actual)
		}
		requestReceived <- struct{}{}
		writer.WriteHeader(http.StatusOK)
	}))
	defer upstreamServer.Close()

	server := &service{
		statusClient: &http.Client{Timeout: time.Second},
	}
	err := server.cancelUpstream(upstream{
		url:   upstreamServer.URL,
		token: "token",
	}, taskID)
	if err != nil {
		t.Fatalf("cancel upstream: %v", err)
	}

	select {
	case <-requestReceived:
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for cancel request")
	}
}

func TestCancelUpstreamAcceptsQueuedCancellation(t *testing.T) {
	upstreamServer := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		writer.WriteHeader(http.StatusAccepted)
	}))
	defer upstreamServer.Close()

	server := &service{statusClient: &http.Client{Timeout: time.Second}}
	if err := server.cancelUpstream(upstream{url: upstreamServer.URL}, "queued-task"); err != nil {
		t.Fatalf("cancel queued upstream task: %v", err)
	}
}

func TestCancelUpstreamRejectsUnsuccessfulStatus(t *testing.T) {
	upstreamServer := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		http.Error(writer, "unavailable", http.StatusServiceUnavailable)
	}))
	defer upstreamServer.Close()

	server := &service{statusClient: &http.Client{Timeout: time.Second}}
	err := server.cancelUpstream(upstream{url: upstreamServer.URL}, "failed-task")
	if err == nil {
		t.Fatal("expected unsuccessful upstream cancellation to fail")
	}
}

func testTask(id, model, path string) *ASRTask {
	ctx, cancel := context.WithCancel(context.Background())
	return &ASRTask{
		ID:           id,
		Status:       StatusPending,
		Model:        model,
		Filename:     filepath.Base(path),
		TempFilePath: path,
		ResultChan:   make(chan ASRTaskResult, 1),
		Ctx:          ctx,
		CancelFunc:   cancel,
	}
}

type trackingReadCloser struct {
	reads int
}

func (body *trackingReadCloser) Read(_ []byte) (int, error) {
	body.reads++
	return 0, os.ErrClosed
}

func (body *trackingReadCloser) Close() error {
	return nil
}

type countingReadCloser struct {
	reader    io.Reader
	bytesRead int
}

func (body *countingReadCloser) Read(buffer []byte) (int, error) {
	count, err := body.reader.Read(buffer)
	body.bytesRead += count
	return count, err
}

func (body *countingReadCloser) Close() error {
	return nil
}

func writeTestAudio(t *testing.T, name string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), name)
	if err := os.WriteFile(path, []byte("audio"), 0o600); err != nil {
		t.Fatalf("write test audio: %v", err)
	}
	return path
}

func newMultipartTranscriptionRequest(t *testing.T, audio string, fields map[string]string) *http.Request {
	t.Helper()
	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	for name, value := range fields {
		if err := writer.WriteField(name, value); err != nil {
			t.Fatalf("write multipart field %s: %v", name, err)
		}
	}
	filePart, err := writer.CreateFormFile("file", "audio.wav")
	if err != nil {
		t.Fatalf("create multipart audio: %v", err)
	}
	if _, err := io.WriteString(filePart, audio); err != nil {
		t.Fatalf("write multipart audio: %v", err)
	}
	if err := writer.Close(); err != nil {
		t.Fatalf("close multipart request: %v", err)
	}
	request := httptest.NewRequest(http.MethodPost, "/v1/audio/transcriptions", &body)
	request.Header.Set("Content-Type", writer.FormDataContentType())
	return request
}

func waitForStartedModel(t *testing.T, started <-chan string) string {
	t.Helper()
	select {
	case model := <-started:
		return model
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for model worker")
		return ""
	}
}

func waitForTaskResult(t *testing.T, task *ASRTask) {
	t.Helper()
	select {
	case result := <-task.ResultChan:
		if result.Err != nil {
			t.Fatalf("task %s failed: %v", task.ID, result.Err)
		}
	case <-time.After(time.Second):
		t.Fatalf("timed out waiting for task %s", task.ID)
	}
}

func TestLoadServiceEnvironmentValidAndDefaults(t *testing.T) {
	t.Setenv("ASR_ENABLE_WHISPERX", "true")
	t.Setenv("ASR_ENABLE_FUNASR", "false")
	t.Setenv("ASR_MAX_CONCURRENT_UPLOADS", "5")

	env, err := loadServiceEnvironment()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !env.whisperxEnabled || env.funasrEnabled {
		t.Fatalf("unexpected bool settings: %+v", env)
	}
	if env.maxConcurrentUploads != 5 {
		t.Fatalf("expected maxConcurrentUploads=5, got %d", env.maxConcurrentUploads)
	}
}

func TestLoadServiceEnvironmentRejectsInvalidValues(t *testing.T) {
	t.Run("invalid_bool", func(t *testing.T) {
		t.Setenv("ASR_ENABLE_WHISPERX", "invalid_bool")
		if _, err := loadServiceEnvironment(); err == nil {
			t.Fatal("expected error for invalid bool")
		}
	})

	t.Run("exceeds_max_int", func(t *testing.T) {
		t.Setenv("ASR_MAX_CONCURRENT_UPLOADS", "2000")
		if _, err := loadServiceEnvironment(); err == nil {
			t.Fatal("expected error for int exceeding max limit")
		}
	})
}

func TestNewServiceFromEnvironmentValidation(t *testing.T) {
	t.Run("missing_token", func(t *testing.T) {
		t.Setenv("ASR_API_TOKEN", "")
		if _, err := newServiceFromEnvironment(); err == nil || !strings.Contains(err.Error(), "ASR_API_TOKEN is required") {
			t.Fatalf("expected ASR_API_TOKEN error, got: %v", err)
		}
	})

	t.Run("both_disabled", func(t *testing.T) {
		t.Setenv("ASR_API_TOKEN", "test-token")
		t.Setenv("ASR_ENABLE_WHISPERX", "false")
		t.Setenv("ASR_ENABLE_FUNASR", "false")
		if _, err := newServiceFromEnvironment(); err == nil || !strings.Contains(err.Error(), "at least one of ASR_ENABLE_WHISPERX or ASR_ENABLE_FUNASR must be true") {
			t.Fatalf("expected at least one engine error, got: %v", err)
		}
	})

	t.Run("missing_whisperx_url", func(t *testing.T) {
		t.Setenv("ASR_API_TOKEN", "test-token")
		t.Setenv("ASR_ENABLE_WHISPERX", "true")
		t.Setenv("ASR_WHISPERX_TOKEN", "wtoken")
		t.Setenv("ASR_WHISPERX_URL", "")
		t.Setenv("ASR_ENABLE_FUNASR", "false")
		if _, err := newServiceFromEnvironment(); err == nil || !strings.Contains(err.Error(), "ASR_WHISPERX_URL is required") {
			t.Fatalf("expected ASR_WHISPERX_URL error, got: %v", err)
		}
	})

	t.Run("success_valid_env", func(t *testing.T) {
		t.Setenv("ASR_API_TOKEN", "test-token")
		t.Setenv("ASR_ENABLE_WHISPERX", "true")
		t.Setenv("ASR_WHISPERX_TOKEN", "wtoken")
		t.Setenv("ASR_WHISPERX_URL", "http://localhost:8000")
		t.Setenv("ASR_ENABLE_FUNASR", "false")

		svc, err := newServiceFromEnvironment()
		if err != nil {
			t.Fatalf("expected success, got error: %v", err)
		}
		if svc == nil || !svc.whisperxEnabled || svc.funasrEnabled {
			t.Fatalf("unexpected service instance: %+v", svc)
		}
	})
}

func TestHealthAndGetConfigHandlers(t *testing.T) {
	gin.SetMode(gin.TestMode)
	svc := &service{
		whisperxEnabled:       true,
		funasrEnabled:         false,
		funasrRealtimeEnabled: true,
		whisperxSingleModel:   false,
	}

	t.Run("healthz", func(t *testing.T) {
		recorder := httptest.NewRecorder()
		c, _ := gin.CreateTestContext(recorder)
		svc.health(c)
		if c.Writer.Status() != http.StatusNoContent {
			t.Fatalf("expected status %d, got %d", http.StatusNoContent, c.Writer.Status())
		}
	})

	t.Run("getConfig", func(t *testing.T) {
		recorder := httptest.NewRecorder()
		c, _ := gin.CreateTestContext(recorder)
		svc.getConfig(c)
		if recorder.Code != http.StatusOK {
			t.Fatalf("expected status %d, got %d", http.StatusOK, recorder.Code)
		}
		if !strings.Contains(recorder.Body.String(), `"whisperx":true`) {
			t.Fatalf("unexpected config response: %s", recorder.Body.String())
		}
	})
}

func TestSystemEndpoint(t *testing.T) {
	gin.SetMode(gin.TestMode)
	upstreamServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer upstreamServer.Close()

	svc := &service{
		whisperxEnabled: true,
		funasrEnabled:   false,
		upstreams: map[string]upstream{
			"whisperx": {url: upstreamServer.URL, token: "token"},
		},
		statusClient: &http.Client{Timeout: time.Second},
	}

	recorder := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(recorder)
	c.Request = httptest.NewRequest(http.MethodGet, "/v1/system", nil)

	svc.system(c)

	if recorder.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d", http.StatusOK, recorder.Code)
	}
	if !strings.Contains(recorder.Body.String(), `"upstream_status":"available"`) {
		t.Fatalf("unexpected system response: %s", recorder.Body.String())
	}
}

func TestAuthenticateMiddleware(t *testing.T) {
	gin.SetMode(gin.TestMode)
	svc := &service{token: "secret-token"}

	t.Run("unauthorized_missing_token", func(t *testing.T) {
		recorder := httptest.NewRecorder()
		c, _ := gin.CreateTestContext(recorder)
		c.Request = httptest.NewRequest(http.MethodGet, "/v1/models", nil)
		svc.authenticate(c)
		if recorder.Code != http.StatusUnauthorized {
			t.Fatalf("expected 401, got %d", recorder.Code)
		}
	})

	t.Run("authorized_correct_token", func(t *testing.T) {
		recorder := httptest.NewRecorder()
		c, _ := gin.CreateTestContext(recorder)
		c.Request = httptest.NewRequest(http.MethodGet, "/v1/models", nil)
		c.Request.Header.Set("Authorization", "Bearer secret-token")
		svc.authenticate(c)
		if recorder.Code == http.StatusUnauthorized {
			t.Fatal("expected request to pass authentication")
		}
	})
}

func TestCancelTaskForModel(t *testing.T) {
	upstreamServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Task-Id") == "test-task" {
			w.WriteHeader(http.StatusOK)
		} else {
			w.WriteHeader(http.StatusBadRequest)
		}
	}))
	defer upstreamServer.Close()

	svc := &service{
		upstreams: map[string]upstream{
			"whisperx": {url: upstreamServer.URL, token: "token"},
		},
		statusClient: &http.Client{Timeout: time.Second},
	}

	t.Run("unsupported_model", func(t *testing.T) {
		if err := svc.cancelTaskForModel("unsupported", "task1"); err == nil {
			t.Fatal("expected error for unsupported model")
		}
	})

	t.Run("model_not_configured", func(t *testing.T) {
		if err := svc.cancelTaskForModel("funasr", "task1"); err == nil {
			t.Fatal("expected error when model is not in upstreams")
		}
	})

	t.Run("successful_cancellation", func(t *testing.T) {
		if err := svc.cancelTaskForModel("whisperx", "test-task"); err != nil {
			t.Fatalf("expected success, got %v", err)
		}
	})
}

