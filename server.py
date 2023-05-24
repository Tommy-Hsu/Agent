import sys
import socket
import selectors
import types
import argparse

sel = selectors.DefaultSelector() # 使得 i/o 用 event 驅動 p.s. 非同步
parser = argparse.ArgumentParser() # 獲取檔案參數

command_list = [ i for i in range(1, 100) ] 

# 
def accept_wrapper(sock):
    conn, addr = sock.accept()  # server to accept this client
    print(f"Accepted connection from {addr}")
    conn.setblocking(False) # client 端關掉 blocking 
    data = types.SimpleNamespace(addr=addr, inb=b"", outb=b"")
    events = selectors.EVENT_READ | selectors.EVENT_WRITE
    sel.register(conn, events, data=data) # client 端可讀可寫

#
def service_connection(key, mask):
    sock = key.fileobj
    data = key.data
    if mask & selectors.EVENT_READ: # 若可以讀取
        recv_data = sock.recv(1024)  # Should be ready to read
        if recv_data:
            print(f"Receive '{recv_data.decode()}' from {data.addr}")
            if recv_data.decode() in command_list: # 已經定義的字串
                data.outb += b"OK"
            else:
                data.outb += b"Wrong command!"
        else:
            print(f"Closing connection to {data.addr}\n")
            sel.unregister(sock)
            sock.close()

    if mask & selectors.EVENT_WRITE: # 若可以寫入
        if data.outb:
            print(f"Send {data.outb!r} to {data.addr}")
            sent = sock.send(data.outb)  # Should be ready to write
            data.outb = data.outb[sent:]

# server 主程式
def server(ip, port):
    lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # [於伺服器與伺服器之間進行串接], [使用TCP(資料流)的方式提供可靠、雙向、串流的通信頻道]
    lsock.bind((ip, port)) # 伺服器窗口
    lsock.listen()
    print(f"Listening on {(ip, port)}")
    lsock.setblocking(False) # 將此socket設成非阻塞
    sel.register(lsock, selectors.EVENT_READ, data=None) # 監聽 server 端

    try:
        while True:
            events = sel.select(timeout=None) # select是不断轮询去监听的socket，socket个数有限制，一般为1024个（文件描述符为1024，该值可以修改）；随着文件描述符数量增加，轮询一回成本增加。
            for key, mask in events:
                if key.data is None: # 初始 accept client
                    accept_wrapper(key.fileobj)
                else: # 只有命令沒有 data 可能要結束
                    service_connection(key, mask)
    except KeyboardInterrupt:
        print("Caught keyboard interrupt, exiting")
    finally:
        sel.close()

if __name__ == '__main__':
    parser.add_argument("--ip", help="The server IP address", required=True)
    parser.add_argument("--port", help="The server port number", type=int, required=True)
    args = parser.parse_args()
    server(args.ip, args.port)