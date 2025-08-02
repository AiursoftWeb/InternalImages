package main

import (
	"context"
	"log"
	"net"
	"os"
	"os/exec"
	"sync"
	"time"

	"github.com/mcstatus-io/mcutil/v4/status"
)

var (
	mcProcessLock sync.Mutex
)

// hasSession 判断 tmux 会话是否存在
func hasSession(name string) bool {
	cmd := exec.Command("tmux", "has-session", "-t", name)
	err := cmd.Run()
	return err == nil
}

// startMinecraft 启动 Minecraft 服务器（放在 tmux 会话 mc 里），并在端口就绪后执行 init 脚本。
func startMinecraft() error {
	mcProcessLock.Lock()
	defer mcProcessLock.Unlock()

	if hasSession("mc") {
		// 已有会话，假定服务器已经在跑
		return nil
	}

	log.Println("在 tmux 会话 mc 中启动 Minecraft 进程……")
	// 用 bash -lc 方便重定向日志
	javaCmdStr := `java -XX:+UseG1GC -Xms4G -Xmx12G -jar /app/papermc.jar --nojline --nogui > /var/log/mc/mc.log 2>&1`
	cmd := exec.Command("tmux", "new-session", "-d", "-s", "mc", "bash", "-lc", javaCmdStr)
	if output, err := cmd.CombinedOutput(); err != nil {
		log.Printf("创建 tmux 会话失败，输出：%s", string(output))
		return err
	}

	// 等待 Minecraft 服务器在 25566 上可连通
	for i := 0; i < 30; i++ {
		conn, err := net.Dial("tcp", "127.0.0.1:25566")
		if err == nil {
			conn.Close()
			break
		}
		time.Sleep(2 * time.Second)
	}

	// 服务器端口可达，执行 init 脚本（脚本本身用 tmux send-keys 注入命令）
	log.Println("检测到 Minecraft 服务器可达，执行 init-commands.sh")
	if out, err := exec.Command("bash", "/app/init-commands.sh").CombinedOutput(); err != nil {
		log.Printf("执行 init-commands.sh 失败: %v, 输出: %s", err, string(out))
	}

	return nil
}

// stopMinecraft 通过 kill tmux session 停掉服务器
func stopMinecraft() error {
	mcProcessLock.Lock()
	defer mcProcessLock.Unlock()

	if !hasSession("mc") {
		log.Println("Minecraft tmux 会话不存在，跳过停止")
		return nil
	}

	log.Println("因无在线玩家，停止 Minecraft 服务器（kill tmux 会话 mc）……")
	if out, err := exec.Command("tmux", "kill-session", "-t", "mc").CombinedOutput(); err != nil {
		log.Printf("kill-session 失败: %v, 输出: %s", err, string(out))
		return err
	}
	log.Println("Minecraft 服务器已停止。")
	return nil
}

// monitorInactivity 周期性检查在线玩家数，连续 8 次为 0 才停服
func monitorInactivity() {
	log.Println("启动在线玩家监测...")
	zeroCount := 0
	for {
		time.Sleep(10 * time.Second)

		if !hasSession("mc") {
			log.Println("Minecraft 服务器未启动，等待启动...")
			zeroCount = 0
			continue
		}

		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		response, err := status.Modern(ctx, "127.0.0.1", 25566)
		cancel()
		if err != nil {
			log.Println("查询 Minecraft 服务器状态失败：", err)
			continue
		}

		if response.Players != nil && response.Players.Online != nil {
			log.Printf("当前在线玩家数：%d\n", *response.Players.Online)
			if *response.Players.Online == 0 {
				zeroCount++
				log.Printf("连续无在线玩家检测次数：%d/8\n", zeroCount)
				if zeroCount >= 8 {
					log.Println("连续8次检测均无在线玩家，停止 Minecraft 服务器")
					stopMinecraft()
					zeroCount = 0
				}
			} else {
				zeroCount = 0
				log.Println("检测到在线玩家，不停止 Minecraft 服务器。")
			}
		} else {
			log.Println("玩家数信息不可用，跳过计数。")
		}
	}
}

// handleConnection 接入时触发，懒惰启动
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

	backend, err := net.Dial("tcp", "127.0.0.1:25566")
	if err != nil {
		log.Println("连接 Minecraft 服务失败：", err)
		return
	}
	defer backend.Close()

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
