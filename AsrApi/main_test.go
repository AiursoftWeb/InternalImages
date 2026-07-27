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
