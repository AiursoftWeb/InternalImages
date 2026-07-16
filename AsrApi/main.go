package main

import (
	"context"
	"errors"
	"io"
	"log"
	"mime/multipart"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/joho/godotenv"
)

const maxUploadSize = 100 << 20

type upstream struct {
	url   string
	model string
	token string
}

type service struct {
	token        string
	upstreams    map[string]upstream
	client       *http.Client
	statusClient *http.Client
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
	router.Static("/assets", "web/dist/assets")
	router.StaticFile("/", "web/dist/index.html")
	router.GET("/healthz", server.health)
	v1 := router.Group("/v1")
	v1.Use(server.authenticate)
	v1.GET("/models", server.models)
	v1.GET("/system", server.system)
	v1.POST("/audio/transcriptions", server.transcribe)
	return router
}

func newServiceFromEnvironment() (*service, error) {
	token := os.Getenv("ASR_API_TOKEN")
	if token == "" {
		return nil, errors.New("ASR_API_TOKEN is required")
	}
	whisperXToken := os.Getenv("ASR_WHISPERX_TOKEN")
	if whisperXToken == "" {
		return nil, errors.New("ASR_WHISPERX_TOKEN is required")
	}
	funASRToken := os.Getenv("ASR_FUNASR_TOKEN")
	if funASRToken == "" {
		return nil, errors.New("ASR_FUNASR_TOKEN is required")
	}

	whisperXURL := strings.TrimRight(os.Getenv("ASR_WHISPERX_URL"), "/")
	funASRURL := strings.TrimRight(os.Getenv("ASR_FUNASR_URL"), "/")
	if whisperXURL == "" || funASRURL == "" {
		return nil, errors.New("ASR_WHISPERX_URL and ASR_FUNASR_URL are required")
	}
	if _, err := url.ParseRequestURI(whisperXURL); err != nil {
		return nil, errors.New("ASR_WHISPERX_URL must be a valid URL")
	}
	if _, err := url.ParseRequestURI(funASRURL); err != nil {
		return nil, errors.New("ASR_FUNASR_URL must be a valid URL")
	}

	return &service{
		token: token,
		upstreams: map[string]upstream{
			"whisperx": {url: whisperXURL, model: environmentOrDefault("ASR_WHISPERX_MODEL", "whisperx"), token: whisperXToken},
			"funasr":   {url: funASRURL, model: environmentOrDefault("ASR_FUNASR_MODEL", "sensevoice"), token: funASRToken},
		},
		client:       &http.Client{Timeout: 10 * time.Minute},
		statusClient: &http.Client{Timeout: 5 * time.Second},
	}, nil
}

func environmentOrDefault(name, defaultValue string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return defaultValue
}

func (s *service) health(c *gin.Context) {
	c.Status(http.StatusNoContent)
}

func (s *service) models(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"object": "list",
		"data": []gin.H{
			{"id": "whisperx", "object": "model", "owned_by": "whisperx"},
			{"id": "funasr", "object": "model", "owned_by": "funasr"},
		},
	})
}

func (s *service) system(c *gin.Context) {
	whisperXStatus := make(chan string, 1)
	funASRStatus := make(chan string, 1)
	go func() {
		whisperXStatus <- s.upstreamStatus(c.Request.Context(), s.upstreams["whisperx"])
	}()
	go func() {
		funASRStatus <- s.upstreamStatus(c.Request.Context(), s.upstreams["funasr"])
	}()

	c.JSON(http.StatusOK, gin.H{
		"status":             "ok",
		"upload_limit_bytes": maxUploadSize,
		"models": []gin.H{
			{"id": "whisperx", "upstream_status": <-whisperXStatus},
			{"id": "funasr", "upstream_status": <-funASRStatus},
		},
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

func (s *service) transcribe(c *gin.Context) {
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, maxUploadSize)
	modelName := c.PostForm("model")
	backend, ok := s.upstreams[modelName]
	if !ok {
		c.JSON(http.StatusBadRequest, gin.H{"error": "model must be whisperx or funasr"})
		return
	}

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
		if err := input.Close(); err != nil {
			log.Printf("close uploaded audio: %v", err)
		}
	}()

	body, contentType := buildUpstreamBody(input, file.Filename, backend.model, c.PostForm("language"), c.PostForm("response_format"))
	request, err := http.NewRequestWithContext(c.Request.Context(), http.MethodPost, backend.url+"/v1/audio/transcriptions", body)
	if err != nil {
		log.Printf("build upstream request: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "cannot create upstream request"})
		return
	}
	request.Header.Set("Content-Type", contentType)
	request.Header.Set("Authorization", "Bearer "+backend.token)

	response, err := s.client.Do(request)
	if err != nil {
		log.Printf("call %s upstream: %v", modelName, err)
		c.JSON(http.StatusBadGateway, gin.H{"error": "model service is unavailable"})
		return
	}
	defer func() {
		if err := response.Body.Close(); err != nil {
			log.Printf("close upstream response: %v", err)
		}
	}()

	c.Header("Content-Type", response.Header.Get("Content-Type"))
	c.Status(response.StatusCode)
	if _, err := io.Copy(c.Writer, response.Body); err != nil {
		log.Printf("write upstream response: %v", err)
	}
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
