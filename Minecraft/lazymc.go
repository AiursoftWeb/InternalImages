package main

import (
	"io"
	"log"
	"net"
	"os"
	"os/exec"
	"sync"
	"time"
)

var (
	mcProcess       *exec.Cmd
	mcProcessLock   sync.Mutex
	activeConnCount int        // 活跃连接数
	connCountLock   sync.Mutex // 保护 activeConnCount 的互斥锁
)

// startMinecraft 启动 Minecraft 进程，并等待 25566 端口就绪。
// 同时延迟执行 /app/init-commands.sh 初始化脚本（可根据需要调整）。
func startMinecraft() error {
	mcProcessLock.Lock()
	defer mcProcessLock.Unlock()

	if mcProcess != nil && mcProcess.Process != nil {
		// 已经启动，无需重复启动
		return nil
	}

	log.Println("启动 Minecraft 进程……")
	// 注意：server.properties 需要预先修改为监听 25566
	cmd := exec.Command("java", "-XX:+UseG1GC", "-Xms4G", "-Xmx12G", "-jar", "/app/papermc.jar", "--nojline", "--nogui")
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Start(); err != nil {
		return err
	}
	mcProcess = cmd

	// 延迟 60 秒后执行 init-commands.sh（可选）
	go func() {
		time.Sleep(60 * time.Second)
		log.Println("执行 init-commands.sh")
		exec.Command("bash", "/app/init-commands.sh").Run()
	}()

	// 等待 Minecraft 服务器在 25566 上就绪（最多等待约 60 秒）
	for i := 0; i < 30; i++ {
		conn, err := net.Dial("tcp", "127.0.0.1:25566")
		if err == nil {
			conn.Close()
			break
		}
		time.Sleep(2 * time.Second)
	}
	return nil
}

// stopMinecraft 杀掉 Minecraft 进程
func stopMinecraft() error {
	mcProcessLock.Lock()
	defer mcProcessLock.Unlock()
	if mcProcess != nil && mcProcess.Process != nil {
		log.Println("因长时间无活跃连接，停止 Minecraft 进程……")
		err := mcProcess.Process.Kill()
		mcProcess = nil
		return err
	}
	return nil
}

// monitorInactivity 定时检查活跃连接数，只有连续10次检测（每次间隔10分钟）都为0时才停止服务器
func monitorInactivity() {
	zeroCount := 0
	for {
		time.Sleep(10 * time.Minute)
		connCountLock.Lock()
		count := activeConnCount
		connCountLock.Unlock()
		log.Println("当前活跃连接数：", count)
		if count == 0 {
			zeroCount++
			log.Printf("连续空连接检测次数: %d\n", zeroCount)
			if zeroCount >= 10 {
				log.Println("连续10次检测均无活跃连接，停止 Minecraft 服务器")
				stopMinecraft()
				zeroCount = 0 // 重置计数器
			}
		} else {
			zeroCount = 0
			log.Println("有活跃连接，不停止 Minecraft 服务器")
		}
	}
}

// handleConnection 处理来自 25565 的每个连接，并将数据转发到 25566
func handleConnection(conn net.Conn) {
	// 增加连接计数
	connCountLock.Lock()
	activeConnCount++
	connCountLock.Unlock()

	// 保证连接结束时减少计数
	defer func() {
		connCountLock.Lock()
		activeConnCount--
		connCountLock.Unlock()
		conn.Close()
	}()

	// 确保 Minecraft 进程已启动
	if err := startMinecraft(); err != nil {
		log.Println("启动 Minecraft 失败：", err)
		return
	}

	// 连接真实 Minecraft 服务
	backend, err := net.Dial("tcp", "127.0.0.1:25566")
	if err != nil {
		log.Println("连接 Minecraft 服务失败：", err)
		return
	}
	defer backend.Close()

	// 双向转发
	go io.Copy(backend, conn)
	io.Copy(conn, backend)
}

func main() {
	go monitorInactivity()

	ln, err := net.Listen("tcp", ":25565")
	if err != nil {
		log.Fatal("监听失败：", err)
	}
	log.Println("LazyMC 加载器已启动，监听端口 25565")
	for {
		conn, err := ln.Accept()
		if err != nil {
			log.Println("Accept 错误：", err)
			continue
		}
		go handleConnection(conn)
	}
}
