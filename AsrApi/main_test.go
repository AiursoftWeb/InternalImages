package main

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
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
	manager := NewTaskManager(1, models)

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

func TestCancelPendingTaskReleasesQueueCapacityAndRemovesFile(t *testing.T) {
	models := map[string]upstream{"whisperx": {}}
	manager := NewTaskManager(1, models)
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
	manager := NewTaskManager(1, models)
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
	manager := NewTaskManager(1, map[string]upstream{"whisperx": {}})
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

func TestCancelRunningTaskRemovesTaskWhenUpstreamCancellationFails(t *testing.T) {
	manager := NewTaskManager(1, map[string]upstream{"whisperx": {}})
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
	manager := NewTaskManager(1, map[string]upstream{"whisperx": {}})
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
	manager := NewTaskManager(1, map[string]upstream{"whisperx": {}})
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
	manager := NewTaskManager(1, map[string]upstream{"whisperx": {}})
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
	manager := NewTaskManager(1, models)
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
	manager := NewTaskManager(1, models)
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
	manager := NewTaskManager(1, models)
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

func writeTestAudio(t *testing.T, name string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), name)
	if err := os.WriteFile(path, []byte("audio"), 0o600); err != nil {
		t.Fatalf("write test audio: %v", err)
	}
	return path
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
