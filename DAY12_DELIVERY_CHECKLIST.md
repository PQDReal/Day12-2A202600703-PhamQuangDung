#  Delivery Checklist — Day 12 Lab Submission

> **Student Name:** _________________________  
> **Student ID:** _________________________  
> **Date:** _________________________

---

##  Submission Requirements

Submit a **GitHub repository** containing:

### 1. Mission Answers (40 points)

Create a file `MISSION_ANSWERS.md` with your answers to all exercises:

```markdown
# Day 12 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found
1. Hardcode secret trực tiếp trong mã nguồn: `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`.
2. Không có cơ chế cấu hình theo môi trường: `DEBUG`, `MAX_TOKENS`, host và port đều bị cố định trong code thay vì đọc từ biến môi trường.
3. Bật chế độ debug/reload khi chạy app: `reload=True`, phù hợp khi phát triển local nhưng không an toàn cho production.
4. App bind vào `localhost`, nên không thể nhận kết nối từ bên ngoài máy/container.
5. Port bị hardcode là `8000`; các nền tảng cloud thường inject biến môi trường `PORT`.
6. Bản develop không có endpoint `/health` hoặc `/ready`, nên cloud platform không thể kiểm tra liveness/readiness.
7. Dùng `print()` để debug thay vì structured logging.
8. Log cả API key, có thể làm lộ secret trong terminal hoặc cloud logs.
9. Không có graceful shutdown hoặc lifecycle cleanup.

### Exercise 1.2: Output khi chạy bản basic

Lệnh chạy:
```bash
cd 01-localhost-vs-production/develop
python app.py
curl http://localhost:8000/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
```

Output server quan sát được:
```text
Starting agent on localhost:8000...
INFO:     Uvicorn running on http://localhost:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [1836] using WatchFiles
INFO:     Started server process [2508]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     127.0.0.1:53236 - "POST /ask HTTP/1.1" 422 Unprocessable Entity
```

Output curl quan sát được:
```json
{"detail":[{"type":"missing","loc":["query","question"],"msg":"Field required","input":null}]}
```

Nhận xét: bản develop có chạy được, nhưng endpoint `/ask` được khai báo là `ask_agent(question: str)`, nên FastAPI hiểu `question` là query parameter. Trong khi đó lệnh curl của lab gửi dữ liệu bằng JSON body, vì vậy request trả về lỗi `422`. Đây là một phát hiện quan trọng về production-readiness: hợp đồng API giữa client và server chưa rõ ràng/chưa nhất quán.

### Exercise 1.3: Comparison table
| Feature | Develop | Production | Why Important? |
|---------|---------|------------|----------------|
| Config | Hardcode trực tiếp trong `app.py` | Đọc từ biến môi trường thông qua `config.py` / `.env` | Cho phép cấu hình khác nhau giữa local/staging/production mà không cần sửa code, đồng thời tránh commit secret |
| Secrets | API key giả và DB URL bị hardcode, thậm chí còn bị log ra | `.env.example` mô tả các secret cần có; giá trị thật lấy từ môi trường | Tránh lộ secret trên Git và cloud logs |
| Host/Port | `host="localhost"`, `port=8000` | Dùng biến môi trường `HOST` và `PORT`, mặc định `0.0.0.0:8000` | Cần thiết cho Docker/Railway/Render vì platform route traffic vào port được inject |
| Request body | Endpoint develop mong đợi query parameter, nên curl gửi JSON trả `422` | Endpoint production đọc JSON body và validate trường `question` | Hợp đồng API rõ ràng giúp tránh mismatch giữa client và server |
| Health check | Không có | `/health` trả status, uptime, version, environment, timestamp | Cloud platform và monitoring có thể phát hiện container lỗi |
| Readiness check | Không có | `/ready` trả trạng thái sẵn sàng hoặc `503` | Load balancer có thể ngừng route traffic khi app chưa khởi tạo xong |
| Logging | Dùng `print()` debug và log cả secret | Structured JSON logging, không log secret | Log dễ parse/tìm kiếm hơn và an toàn hơn trong production |
| Shutdown | Không có lifecycle handling | Có lifespan startup/shutdown và SIGTERM handler | Hỗ trợ graceful shutdown khi deploy/restart |
| CORS | Không cấu hình | Allowed origins có thể cấu hình | Tích hợp browser/API an toàn hơn |
| Debug reload | Luôn `reload=True` | Chỉ reload khi `DEBUG=true` | Tránh reloader process và overhead không cần thiết trong production |

Output khi chạy bản production:
```bash
cd 01-localhost-vs-production/production
cp .env.example .env
pip install -r requirements.txt
python app.py
curl http://localhost:8000/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
```

Output server quan sát được:
```text
WARNING:root:OPENAI_API_KEY not set — using mock LLM
INFO:     Started server process [4416]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     127.0.0.1:56795 - "POST /ask HTTP/1.1" 200 OK
```

Output curl quan sát được:
```json
{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","model":"gpt-4o-mini"}
```

Kết luận Part 1: bản production khắc phục các anti-pattern chính của bản localhost bằng cách dùng cấu hình từ môi trường, xử lý JSON request đúng hơn, bổ sung health/readiness endpoints, structured logging và graceful lifecycle handling. Bản develop hữu ích để minh họa vì sao "chạy được trên máy mình" vẫn chưa đủ để deploy lên production.

## Part 2: Docker

### Exercise 2.1: Dockerfile questions
1. Base image: bản develop dùng `python:3.11`. Đây là full Python image nên dễ hiểu và dễ debug, nhưng kích thước lớn.
2. Working directory: `/app`. Đây là thư mục làm việc bên trong container, nơi copy code và chạy ứng dụng.
3. Vì sao copy `requirements.txt` trước: Docker cache theo layer. Nếu dependencies không đổi, layer `pip install` được cache lại; chỉ thay đổi code thì build nhanh hơn.
4. `CMD` vs `ENTRYPOINT`: `CMD` là lệnh mặc định và dễ override khi `docker run`; `ENTRYPOINT` cố định command chính của container hơn, thường dùng khi image luôn chạy một executable cụ thể.

### Exercise 2.2: Build và run basic container

Lệnh build đúng cần chạy từ project root vì Dockerfile dùng path `02-docker/develop/...` và `utils/...`:
```bash
cd day12_ha-tang-cloud_va_deployment
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -p 8000:8000 my-agent:develop
```

Output container:
```text
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     172.17.0.1:49384 - "POST /ask HTTP/1.1" 422 Unprocessable Entity
INFO:     172.17.0.1:35744 - "POST /ask HTTP/1.1" 422 Unprocessable Entity
INFO:     172.17.0.1:52794 - "POST /ask HTTP/1.1" 422 Unprocessable Entity
```

Lệnh test theo `CODE_LAB.md`:
```bash
curl http://localhost:8000/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"question": "What is Docker?"}'
```

Output:
```json
{"detail":[{"type":"missing","loc":["query","question"],"msg":"Field required","input":null}]}
```

Nhận xét: container đã chạy thành công, nhưng endpoint vẫn trả `422` khi gửi JSON body vì code bản develop khai báo `question: str`, khiến FastAPI hiểu `question` là query parameter. Docker đóng gói đúng hành vi hiện có của app; nó không tự sửa mismatch trong API contract.

### Exercise 2.3: Multi-stage build

Stage 1 `builder`:
- Dùng `python:3.11-slim AS builder`.
- Cài build dependencies như `gcc`, `libpq-dev`.
- Cài Python packages bằng `pip install --user` vào `/root/.local`.

Stage 2 `runtime`:
- Dùng `python:3.11-slim AS runtime`.
- Tạo non-root user `appuser`.
- Chỉ copy dependencies đã cài từ builder và source code cần thiết.
- Thêm `HEALTHCHECK`.
- Chạy app bằng `uvicorn`.

Vì sao image nhỏ hơn: runtime image không giữ build tools/compiler/cache không cần thiết, chỉ giữ runtime Python, dependencies đã cài và source code.

Lưu ý khi build: Dockerfile production cũng cần build từ project root, không phải từ `02-docker/production`, vì có các dòng `COPY 02-docker/production/...` và `COPY utils/mock_llm.py ...`.

Output kiểm tra image size trong PowerShell:
```powershell
docker images my-agent:develop
```

```text
i Info ->   U  In Use
IMAGE              ID             DISK USAGE   CONTENT SIZE   EXTRA
my-agent:develop   79217902bec3       1.66GB          424MB    U
```

### Exercise 2.3: Image size comparison
- Develop: `1.66GB`
- Production / Advanced: `236MB`
- Difference: giảm khoảng `85.8%` so với image develop.

Output kiểm tra image trong Git Bash:
```bash
docker images | grep my-agent
```

```text
my-agent:advanced   97bac46884b5        236MB         56.6MB
my-agent:develop    79217902bec3       1.66GB          424MB
my-agent:latest     18ec8bd8d8d4       1.66GB          424MB
```

Output kiểm tra riêng image develop trong PowerShell/Docker Desktop:
```powershell
docker images my-agent:develop
```

```text
i Info ->   U  In Use
IMAGE              ID             DISK USAGE   CONTENT SIZE   EXTRA
my-agent:develop   79217902bec3       1.66GB          424MB    U
```

Ghi chú môi trường: trong Git Bash/MINGW64 dùng `grep`; trong PowerShell mới dùng `Select-String`.

### Exercise 2.4: Docker Compose stack

Architecture diagram:
```text
Client
  |
  v
Nginx reverse proxy / load balancer :80
  |
  v
Agent FastAPI service :8000
  |
  +--> Redis :6379, dùng cho cache/session/rate limiting
  |
  +--> Qdrant :6333, vector database cho RAG
```

Các service trong `docker-compose.yml`:
- `agent`: FastAPI AI agent, build từ Dockerfile production.
- `redis`: cache/session/rate limiting.
- `qdrant`: vector database.
- `nginx`: reverse proxy/load balancer, expose port `80` và `443`.

Nhận xét: stack production mô phỏng kiến trúc deploy thực tế hơn bản single container, với reverse proxy phía trước và backing services phía sau.

Output test Docker Compose stack:
```bash
curl http://localhost/health
```

```json
{"status":"ok","uptime_seconds":152.9,"version":"2.0.0","timestamp":"2026-06-12T08:43:20.986226"}
```

```bash
curl http://localhost/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"question": "Explain microservices"}'
```

```json
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

Kết luận Exercise 2.4: Docker Compose stack đã chạy thành công qua Nginx tại `http://localhost`. `/health` trả `200 OK`, và `/ask` nhận JSON body đúng ở bản production stack.

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment
- URL: https://docker-tutorial-production-cace.up.railway.app
- Screenshot: chưa thêm vào repo ở thời điểm ghi nhận này.

Các biến môi trường đã set trên Railway:
```bash
railway variables set PORT=8000
railway variables set AGENT_API_KEY=my-secret-key
```

Output:
```text
Set variables PORT
Set variables AGENT_API_KEY
```

Tạo/lấy service domain:
```bash
railway domain
```

Output:
```text
Service Domain created:
https://docker-tutorial-production-cace.up.railway.app
```

Lỗi khi dùng domain mẫu trong tài liệu:
```bash
curl http://student-agent-domain/health
curl http://student-agent-domain/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"question": ""}'
```

Output:
```text
curl: (6) Could not resolve host: student-agent-domain
```

Nhận xét: `student-agent-domain` chỉ là placeholder trong `CODE_LAB.md`, cần thay bằng domain thật Railway cấp.

Health check với domain thật:
```bash
curl https://docker-tutorial-production-cace.up.railway.app/health
```

Output:
```json
{"status":"ok","uptime_seconds":344.0,"platform":"Railway","timestamp":"2026-06-12T09:12:46.706419+00:00"}
```

Test `/ask` với question rỗng:
```bash
curl https://docker-tutorial-production-cace.up.railway.app/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"question": ""}'
```

Output:
```json
{"detail":"question required"}
```

Nhận xét: endpoint hoạt động và validate input đúng; question rỗng bị từ chối.

Lỗi quote trong Git Bash:
```bash
curl https://docker-tutorial-production-cace.up.railway.app/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"question": "What's your condition?"}'
```

Kết quả: terminal chuyển sang prompt `>` và phải `Ctrl+C` vì dấu `'` trong `What's` làm vỡ chuỗi single-quote của Bash.

Lỗi sai endpoint:
```bash
curl https://docker-tutorial-production-cace.up.railway.app/askk -X POST \
  -H "Content-Type: application/json" \
  -d '{"question": "How are you?"}'
```

Output:
```json
{"detail":"Not Found"}
```

Test `/ask` thành công:
```bash
curl https://docker-tutorial-production-cace.up.railway.app/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"question": "How are you?"}'
```

Output:
```json
{"question":"How are you?","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","platform":"Railway"}
```

Kết luận Exercise 3.1: Railway deployment thành công. Public URL hoạt động, `/health` trả `200 OK`, `/ask` nhận JSON body đúng và trả response từ mock LLM.

### Exercise 3.2: Render deployment

- URL: https://ai-agent-f10k.onrender.com
- Blueprint path dùng trên Render: `03-cloud-deployment/render/render.yaml`
- Ghi chú cấu hình: đã sửa `render.yaml` để thêm `ipAllowList: []` cho Redis và `rootDir: 03-cloud-deployment/railway` cho web service, vì Render build từ root repo nếu không chỉ định root directory.

Health check:
```bash
curl https://ai-agent-f10k.onrender.com/health
```

Output:
```json
{"status":"ok","uptime_seconds":71.7,"platform":"Railway","timestamp":"2026-06-12T09:44:12.988829+00:00"}
```

Lỗi khi POST vào root `/`:
```bash
curl https://ai-agent-f10k.onrender.com -X POST \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello from Render"}'
```

Output:
```json
{"detail":"Method Not Allowed"}
```

Nhận xét: root `/` chỉ hỗ trợ `GET`, nên POST vào root trả `405 Method Not Allowed`. Endpoint đúng để hỏi agent là `/ask`.

Test `/ask` thành công:
```bash
curl https://ai-agent-f10k.onrender.com/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello from Render"}'
```

Output:
```json
{"question":"Hello from Render","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","platform":"Railway"}
```

So sánh `render.yaml` và `railway.toml`:
- `railway.toml` cấu hình build/deploy cho một service Railway, dùng `startCommand`, `healthcheckPath`, restart policy và set biến môi trường qua Railway CLI/Dashboard.
- `render.yaml` là Blueprint IaC, có thể khai báo nhiều service cùng lúc như web service `ai-agent` và Redis `agent-cache`.
- Render cần chỉ rõ `rootDir` trong repo dạng monorepo/folder lab; Railway deploy trực tiếp từ folder `03-cloud-deployment/railway`.
- Render Redis yêu cầu `ipAllowList`; Railway example không khai báo Redis service trong `railway.toml`.

Kết luận Exercise 3.2: Render deployment thành công. Public URL hoạt động, `/health` trả `200 OK`, và `/ask` trả response đúng khi gọi đúng endpoint.

## Part 4: API Security

### Exercise 4.1-4.3: Test results
#### Exercise 4.1: API Key authentication

Chạy app trong `04-api-gateway/develop`:
```bash
cd 04-api-gateway/develop
python app.py
```

Output server:
```text
API Key: demo-key-change-in-production
Test: curl -H 'X-API-Key: demo-key-change-in-production' http://localhost:8000/ask?question=hello
INFO:     Will watch for changes in these directories: ['C:\\Users\\ThePake\\Desktop\\Applied AI VinUni\\lab12\\day12_ha-tang-cloud_va_deployment\\04-api-gateway\\develop']
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [4672] using WatchFiles
INFO:     Started server process [15108]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     127.0.0.1:54353 - "POST /ask HTTP/1.1" 401 Unauthorized
INFO:     127.0.0.1:54372 - "POST /ask HTTP/1.1" 403 Forbidden
```

Test không có API key:
```bash
curl http://localhost:8000/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
```

Output:
```json
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

Kết quả: request không có key bị từ chối với `401 Unauthorized`.

Test với sai API key:
```bash
curl http://localhost:8000/ask -X POST \
  -H "X-API-Key: secret-key-123" \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
```

Output:
```json
{"detail":"Invalid API key."}
```

Kết quả: request có key nhưng sai giá trị bị từ chối với `403 Forbidden`.

API key được check trong hàm `verify_api_key()` của `04-api-gateway/develop/app.py`:
- Nếu thiếu header `X-API-Key`, app raise `HTTPException(status_code=401)`.
- Nếu key không khớp `API_KEY`, app raise `HTTPException(status_code=403)`.
- `API_KEY` được đọc từ biến môi trường `AGENT_API_KEY`; nếu không set thì dùng mặc định `demo-key-change-in-production`.

Cách rotate key: thay đổi biến môi trường `AGENT_API_KEY` khi chạy app hoặc trên cloud platform, sau đó restart/redeploy service. Không cần sửa code.

Nhận xét: lần test dùng `secret-key-123` bị `403` vì app hiện đang dùng key mặc định `demo-key-change-in-production`. Muốn request thành công thì cần set env:
```bash
export AGENT_API_KEY=secret-key-123
python app.py
```
hoặc gọi bằng đúng key mặc định:
```bash
curl http://localhost:8000/ask -X POST \
  -H "X-API-Key: demo-key-change-in-production" \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
```

### Exercise 4.4: Cost guard implementation
[Explain your approach]

## Part 5: Scaling & Reliability

### Exercise 5.1-5.5: Implementation notes
[Your explanations and test results]
```

---

### 2. Full Source Code - Lab 06 Complete (60 points)

Your final production-ready agent with all files:

```
your-repo/
├── app/
│   ├── main.py              # Main application
│   ├── config.py            # Configuration
│   ├── auth.py              # Authentication
│   ├── rate_limiter.py      # Rate limiting
│   └── cost_guard.py        # Cost protection
├── utils/
│   └── mock_llm.py          # Mock LLM (provided)
├── Dockerfile               # Multi-stage build
├── docker-compose.yml       # Full stack
├── requirements.txt         # Dependencies
├── .env.example             # Environment template
├── .dockerignore            # Docker ignore
├── railway.toml             # Railway config (or render.yaml)
└── README.md                # Setup instructions
```

**Requirements:**
-  All code runs without errors
-  Multi-stage Dockerfile (image < 500 MB)
-  API key authentication
-  Rate limiting (10 req/min)
-  Cost guard ($10/month)
-  Health + readiness checks
-  Graceful shutdown
-  Stateless design (Redis)
-  No hardcoded secrets

---

### 3. Service Domain Link

Create a file `DEPLOYMENT.md` with your deployed service information:

```markdown
# Deployment Information

## Public URL
https://your-agent.railway.app

## Platform
Railway / Render / Cloud Run

## Test Commands

### Health Check
```bash
curl https://your-agent.railway.app/health
# Expected: {"status": "ok"}
```

### API Test (with authentication)
```bash
curl -X POST https://your-agent.railway.app/ask \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
```

## Environment Variables Set
- PORT
- REDIS_URL
- AGENT_API_KEY
- LOG_LEVEL

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
```

##  Pre-Submission Checklist

- [ ] Repository is public (or instructor has access)
- [ ] `MISSION_ANSWERS.md` completed with all exercises
- [ ] `DEPLOYMENT.md` has working public URL
- [ ] All source code in `app/` directory
- [ ] `README.md` has clear setup instructions
- [ ] No `.env` file committed (only `.env.example`)
- [ ] No hardcoded secrets in code
- [ ] Public URL is accessible and working
- [ ] Screenshots included in `screenshots/` folder
- [ ] Repository has clear commit history

---

##  Self-Test

Before submitting, verify your deployment:

```bash
# 1. Health check
curl https://your-app.railway.app/health

# 2. Authentication required
curl https://your-app.railway.app/ask
# Should return 401

# 3. With API key works
curl -H "X-API-Key: YOUR_KEY" https://your-app.railway.app/ask \
  -X POST -d '{"user_id":"test","question":"Hello"}'
# Should return 200

# 4. Rate limiting
for i in {1..15}; do 
  curl -H "X-API-Key: YOUR_KEY" https://your-app.railway.app/ask \
    -X POST -d '{"user_id":"test","question":"test"}'; 
done
# Should eventually return 429
```

---

##  Submission

**Submit your GitHub repository URL:**

```
https://github.com/your-username/day12-agent-deployment
```

**Deadline:** 17/4/2026

---

##  Quick Tips

1.  Test your public URL from a different device
2.  Make sure repository is public or instructor has access
3.  Include screenshots of working deployment
4.  Write clear commit messages
5.  Test all commands in DEPLOYMENT.md work
6.  No secrets in code or commit history

---

##  Need Help?

- Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- Review [CODE_LAB.md](CODE_LAB.md)
- Ask in office hours
- Post in discussion forum

---

**Good luck! **
