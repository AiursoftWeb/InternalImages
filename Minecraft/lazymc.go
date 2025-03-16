package main

import (
	"context"
	"io"
	"log"
	"net"
	"os"
	"os/exec"
	"sync"
	"time"

	"github.com/mcstatus-io/mcutil/v4/status"
)

var (
	mcProcess     *exec.Cmd
	mcProcessLock sync.Mutex
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
		log.Println("因长时间无在线玩家，停止 Minecraft 进程……")
		err := mcProcess.Process.Kill()
		log.Println("Minecraft 进程已停止。节省资源。下次连接时会自动重启。")
		mcProcess = nil
		return err
	} else {
		log.Println("Minecraft 进程未启动，无需停止")
	}
	return nil
}

// monitorInactivity 定时查询在线玩家数，只有连续 100 次（约 1000 秒）检测到在线玩家数为 0 时，才停止 Minecraft 服务器。
func monitorInactivity() {
	log.Println("启动在线玩家监测...")
	zeroCount := 0
	for {
		time.Sleep(10 * time.Second)

		// 如果 Minecraft 进程未启动，跳过检测
		if mcProcess == nil || mcProcess.Process == nil {
			log.Println("Minecraft 服务器未启动，等待启动...")
			zeroCount = 0
			continue
		}

		// 使用 mcutil 查询服务器状态（需 1.7+ 的 netty 服务器）
		ctx, cancel := context.WithTimeout(context.Background(), time.Second*5)
		response, err := status.Modern(ctx, "127.0.0.1", 25566)
		resp := response
		cancel()
		if err != nil {
			log.Println("查询 Minecraft 服务器状态失败：", err)
			// 查询出错时不增加计数，防止误杀
			continue
		}

		log.Printf("当前在线玩家数：%d\n", resp.Players.Online)
		if resp.Players.Online != nil && *resp.Players.Online == 0 {
			zeroCount++
			log.Printf("连续无在线玩家检测次数：%d/100\n", zeroCount)
			if zeroCount >= 100 {
				log.Println("连续100次检测均无在线玩家，停止 Minecraft 服务器")
				stopMinecraft()
				zeroCount = 0 // 重置计数器
			}
		} else {
			zeroCount = 0
			log.Println("检测到在线玩家，不停止 Minecraft 服务器。")
		}
	}
}

// handleConnection 处理来自 25565 的每个连接，并将数据转发到 25566。
func handleConnection(conn net.Conn) {
	defer func() {
		log.Println("关闭连接：", conn.RemoteAddr())
		conn.Close()
	}()

	log.Println("处理连接：", conn.RemoteAddr())
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

	// 双向转发数据
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
		log.Println("新连接：", conn.RemoteAddr())
		go handleConnection(conn)
	}
}
