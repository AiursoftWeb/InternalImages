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
	activeConnCount int        // 活跃连接数（仅计入保持至少30秒的连接）
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
		log.Println("Minecraft 进程已停止。这是为了节省资源。下次连接时会自动重启。")
		mcProcess = nil
		return err
	} else {
		log.Println("Minecraft 进程未启动，无需停止")
	}
	return nil
}

// monitorInactivity 定时检查活跃连接数，只有连续100次检测均无活跃连接时，也就是1000秒（约16分钟）后，才停止 Minecraft 服务器。
// 这样可以避免频繁启停 Minecraft 服务器，节省资源。
func monitorInactivity() {
	log.Println("启动空连接检测...")
	zeroCount := 0
	for {
		time.Sleep(10 * time.Second)
		// 如果 Minecraft 进程根本没有启动，等待启动
		if mcProcess == nil || mcProcess.Process == nil {
			log.Println("Minecraft 服务器未启动，等待启动...")
			zeroCount = 0
			continue
		}
		connCountLock.Lock()
		count := activeConnCount
		connCountLock.Unlock()
		log.Println("当前活跃连接数：", count)
		if count == 0 {
			zeroCount++
			log.Printf("连续空连接检测次数: %d/100\n", zeroCount)
			if zeroCount >= 100 {
				log.Println("连续100次检测均无活跃连接，停止 Minecraft 服务器")
				stopMinecraft()
				zeroCount = 0 // 重置计数器
			}
		} else {
			zeroCount = 0
			log.Println("有活跃连接，不停止 Minecraft 服务器。 空连接检测次数重置为0。")
		}
	}
}

// handleConnection 处理来自 25565 的每个连接，并将数据转发到 25566。
// 只有保持连接至少30秒，才算作活跃连接。
func handleConnection(conn net.Conn) {
	log.Println("处理连接：", conn.RemoteAddr())

	// 创建一个 channel 用于通知连接关闭
	closed := make(chan struct{})
	// 使用互斥锁保护 active 标志
	var mu sync.Mutex
	active := false

	// 启动一个定时器，30秒后检查连接是否仍然活跃
	timer := time.NewTimer(30 * time.Second)
	go func() {
		select {
		case <-timer.C:
			// 只有连接未关闭时才将其标记为活跃
			select {
			case <-closed:
				// 连接已关闭，不标记为活跃
				return
			default:
				mu.Lock()
				active = true
				mu.Unlock()
				connCountLock.Lock()
				activeConnCount++
				log.Println("连接已保持30秒，计入活跃连接，当前活跃连接数：", activeConnCount)
				connCountLock.Unlock()
			}
		case <-closed:
			if !timer.Stop() {
				<-timer.C
			}
		}
	}()

	// 确保 Minecraft 进程已启动
	if err := startMinecraft(); err != nil {
		log.Println("启动 Minecraft 失败：", err)
		conn.Close()
		return
	}

	// 连接真实 Minecraft 服务
	backend, err := net.Dial("tcp", "127.0.0.1:25566")
	if err != nil {
		log.Println("连接 Minecraft 服务失败：", err)
		conn.Close()
		return
	}
	defer backend.Close()

	// 双向转发数据
	go io.Copy(backend, conn)
	io.Copy(conn, backend)

	// 当双向转发结束时，关闭连接，清理定时器和活跃计数
	close(closed)
	mu.Lock()
	wasActive := active
	mu.Unlock()
	if wasActive {
		connCountLock.Lock()
		activeConnCount--
		log.Println("关闭连接：", conn.RemoteAddr(), "当前活跃连接数：", activeConnCount)
		connCountLock.Unlock()
	} else {
		log.Println("连接未达到30秒，不计入活跃连接：", conn.RemoteAddr())
	}
	conn.Close()
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
		log.Println("新连接：", conn.RemoteAddr())
		go handleConnection(conn)
	}
}
