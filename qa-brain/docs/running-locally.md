# QA Brain — วิธีรันโปรเจกต์บนเครื่อง (Local)

**ทดสอบแล้วจริงบนเครื่องนี้ (2026-07-04):** postgres รันอยู่, seed user แล้ว, login ได้, frontend เชื่อม backend ได้ครบ

---

## 0. Pre-flight — เช็ค port 8000 ก่อน (สำคัญ)

บนเครื่องนี้พบว่า **port 8000 ถูก intercept โดยโปรแกรมอื่น (OrbStack/Kong ของโปรเจกต์อื่น)** ทำให้ backend ตอบ `403 Blocked request` แทนที่จะเป็น response จริง — ไม่เกี่ยวกับ QA Brain เลย แต่ต้องรู้ก่อนรัน

เช็คก่อนเสมอ:
```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/openapi.json
```
- ได้ `200` → ใช้ port 8000 ตามปกติได้เลย ข้ามไปขั้นตอนที่ 1
- ได้ `403` หรืออย่างอื่นที่ไม่ใช่ 200/404 → มี process อื่นชนกันอยู่ ให้ใช้ port อื่นแทน (คู่มือนี้ใช้ **8010** เป็นตัวอย่าง) ตามขั้นตอนด้านล่าง

---

## 1. Database (Postgres) — เปิดครั้งเดียวค้างไว้ได้

```bash
cd qa-brain
docker compose up -d postgres
```
เช็คว่ารันอยู่: `docker ps | grep qa-brain-postgres`

## 2. สร้าง User สำหรับ Login (ทำครั้งแรกครั้งเดียว)

ไม่มีหน้าสมัครสมาชิก (ตั้งใจออกแบบไว้แบบนี้ — เป็น internal tool) ต้องสร้าง user ผ่านสคริปต์:

```bash
cd qa-brain/backend
source .venv/bin/activate   # ถ้ายังไม่มี .venv: python3 -m venv .venv && pip install -r requirements.txt
python -m scripts.seed_user qa@extosoft.com --password Test1234! --role qa_engineer
```
รันซ้ำได้เรื่อยๆ (จะ update password ให้ถ้า user มีอยู่แล้ว)

## 3. Start Backend

**ถ้า port 8000 ใช้ได้ปกติ (จาก step 0):**
```bash
cd qa-brain/backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**ถ้า port 8000 ติดปัญหา ให้ใช้ port อื่นแทน (ตัวอย่างใช้ 8010):**
```bash
cd qa-brain/backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8010
```

เช็คว่าใช้ได้: `curl http://localhost:<PORT>/openapi.json` ต้องได้ JSON กลับมา ไม่ใช่ error page

## 4. Start Frontend

**ถ้า backend อยู่ที่ port 8000 (ค่า default):**
```bash
cd qa-brain/frontend
npm install   # ครั้งแรกครั้งเดียว
npm run dev
```

**ถ้า backend อยู่ที่ port อื่น (เช่น 8010 จาก step 3) ต้องบอก frontend ด้วย:**
```bash
cd qa-brain/frontend
npm install   # ครั้งแรกครั้งเดียว
VITE_API_URL=http://localhost:8010 VITE_WS_URL=ws://localhost:8010 npm run dev
```

เปิดเบราว์เซอร์ไปที่ **http://localhost:5173** จะ redirect ไปหน้า `/login` อัตโนมัติ

## 5. Login

- Email: `qa@extosoft.com`
- Password: `Test1234!`

(หรือ email/password ที่สร้างเองจาก step 2)

## 6. เริ่มใช้งาน

พิมพ์คำสั่งในแชทตาม [usage-guide.md](usage-guide.md) — เช่น:
```
Explore http://localhost:5173/login and generate a script
```

---

## Troubleshooting

| อาการ | สาเหตุที่เป็นไปได้ | วิธีแก้ |
|---|---|---|
| `curl .../openapi.json` ได้ `403 Blocked request` | port ชนกับโปรแกรมอื่น (พบบนเครื่องนี้ว่าเป็น OrbStack/Kong) | เปลี่ยนไปใช้ port อื่น (step 0) |
| Login ไม่ผ่าน | ยังไม่ได้ seed user หรือรหัสผ่านผิด | รัน step 2 ใหม่ |
| แชทไม่ตอบ/ค้าง | backend ไม่ได้รัน หรือ frontend ชี้ผิด port | เช็ค `VITE_API_URL`/`VITE_WS_URL` ตรงกับ port ที่ backend รันจริง |
| Qwen call error/timeout | endpoint ไม่เสถียร (รู้อยู่แล้ว) | พิมพ์คำสั่งเดิมซ้ำ |
| ต้องการ AI จริงจาก Claude (7 tools ที่เหลือ) | `ANTHROPIC_API_KEY` ใน `.env` ยังเป็น placeholder | ใส่ key จริง หรือปล่อย `MOCK_MODE=true` ไว้เพื่อ demo แบบ mock |
