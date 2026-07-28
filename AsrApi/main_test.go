package main

import (
	"context"
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

	if !manager.Cancel(cancelledTask.ID, nil) {
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
	if !manager.Cancel(task.ID, func(model, taskID string) {
		cancelledModel = model
		cancelledTaskID = taskID
	}) {
		t.Fatal("expected running task cancellation to succeed")
	}
	if cancelledModel != task.Model {
		t.Fatalf("expected cancelled model %q, got %q", task.Model, cancelledModel)
	}
	if cancelledTaskID != task.ID {
		t.Fatalf("expected cancelled task ID %q, got %q", task.ID, cancelledTaskID)
	}
}

func TestCancelRunningTaskPublishesResultBeforeCancellingUpstream(t *testing.T) {
	manager := NewTaskManager(1, map[string]upstream{"whisperx": {}})
	task := testTask("running-task", "whisperx", "")
	if err := manager.Add(task); err != nil {
		t.Fatalf("add running task: %v", err)
	}
	manager.waitForPendingTask(manager.queues["whisperx"])

	cancelStarted := make(chan struct{})
	releaseCancel := make(chan struct{})
	cancelled := make(chan bool, 1)
	go func() {
		cancelled <- manager.Cancel(task.ID, func(_, _ string) {
			close(cancelStarted)
			<-releaseCancel
		})
	}()

	select {
	case <-cancelStarted:
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for upstream cancellation")
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
		t.Fatal("cancellation result was blocked by upstream cancellation")
	}

	if err := manager.Add(testTask(task.ID, "whisperx", "")); err == nil {
		t.Fatal("expected task ID to remain reserved during upstream cancellation")
	}
	close(releaseCancel)
	if !<-cancelled {
		t.Fatal("expected running task cancellation to succeed")
	}
}

func TestCancelledWorkerDoesNotDeleteReplacementTask(t *testing.T) {
	manager := NewTaskManager(1, map[string]upstream{"whisperx": {}})
	cancelledTask := testTask("reused-task", "whisperx", "")
	if err := manager.Add(cancelledTask); err != nil {
		t.Fatalf("add cancelled task: %v", err)
	}
	manager.waitForPendingTask(manager.queues["whisperx"])
	if !manager.Cancel(cancelledTask.ID, nil) {
		t.Fatal("expected running task cancellation to succeed")
	}

	replacementTask := testTask(cancelledTask.ID, "whisperx", "")
	if err := manager.Add(replacementTask); err != nil {
		t.Fatalf("add replacement task: %v", err)
	}
	if manager.finishTask(cancelledTask, ASRTaskResult{StatusCode: http.StatusOK}) {
		t.Fatal("expected cancelled worker result not to be published")
	}

	manager.mu.RLock()
	currentTask := manager.tasks[replacementTask.ID]
	manager.mu.RUnlock()
	if currentTask != replacementTask {
		t.Fatal("expected replacement task to remain registered")
	}
}

func TestCancelUnknownTaskDoesNotCallUpstream(t *testing.T) {
	manager := NewTaskManager(1, map[string]upstream{"whisperx": {}})
	cancelCalled := false

	if manager.Cancel("unknown-task", func(_, _ string) {
		cancelCalled = true
	}) {
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
		upstreams:   models,
		client:      &http.Client{Timeout: time.Second},
		taskManager: manager,
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
	server.cancelUpstream(upstream{
		url:   upstreamServer.URL,
		token: "token",
	}, taskID)

	select {
	case <-requestReceived:
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for cancel request")
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
