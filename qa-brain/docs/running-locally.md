# QA Brain — วิธีรันโปรเจกต์บนเครื่อง (Local)

**ทดสอบแล้วจริงบนเครื่องนี้ (2026-07-04):** postgres รันอยู่, seed user แล้ว, login ได้, frontend เชื่อม backend ได้ครบ

---

## -1. เช็คก่อนว่ามี process เก่าค้างอยู่ไหม (สำคัญมาก — ข้ามขั้นตอนนี้แล้วจะงงว่าทำไม "กดอะไรไม่ได้")

ถ้าเคยรัน `npm run dev` หรือ `uvicorn` ค้างไว้จาก terminal อื่น/ครั้งก่อน แล้วเปิดใหม่โดยไม่ปิดของเก่า **vite จะ auto-bump ไป port ถัดไป (5174, 5175, ...) โดยไม่บอกชัดเจน** ทำให้เปิด browser ผิด instance (ไปเจอของเก่าที่ชี้ backend คนละตัว) — อาการที่เจอจริง: login วนซ้ำๆ ไม่จบ, ปุ่มกดเหมือนไม่ทำงาน

เช็คก่อนเริ่มทุกครั้ง:
```bash
ps aux | grep -E "vite|uvicorn" | grep -v grep
lsof -i :5173 -i :5174 -i :8000 -i :8010 -i :8030 2>/dev/null | grep LISTEN
```
ถ้าเจอ process ค้างที่ไม่ใช่ของรอบนี้ ให้ `kill <PID>` ทิ้งก่อน แล้วค่อยเริ่มขั้นตอนถัดไป

---

## 0. Pre-flight — เช็ค port 8000 ก่อน

บนเครื่องนี้พบว่า **port 8000 ถูก intercept โดยโปรแกรมอื่น (OrbStack/Kong ของโปรเจกต์อื่น)** ทำให้ backend ตอบ `403 Blocked request` แทนที่จะเป็น response จริง — ไม่เกี่ยวกับ QA Brain เลย แต่ต้องรู้ก่อนรัน

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/openapi.json
```
- ได้ `200` → ใช้ port 8000 ตามปกติได้เลย ข้ามไปขั้นตอนที่ 1
- ได้ `403` หรืออย่างอื่นที่ไม่ใช่ 200 → มี process อื่นชนกันอยู่ ให้เลือก port อื่นแทน (คู่มือนี้ใช้ **8010** เป็นตัวอย่าง — เลือกเลขอะไรก็ได้ที่ว่าง แค่ใช้ตัวเดียวกันตลอดทั้ง step 3-4)

---

## 1. Database (Postgres) — เปิดครั้งเดียวค้างไว้ได้

```bash
cd qa-brain
docker compose up -d postgres
```
เช็คว่ารันอยู่: `docker ps | grep qa-brain-postgres`

## 2. สร้าง User สำหรับ Login

ไม่มีหน้าสมัครสมาชิก (ตั้งใจออกแบบไว้แบบนี้ — เป็น internal tool) ต้องสร้าง user ผ่านสคริปต์ (ทำครั้งแรกครั้งเดียว รันซ้ำได้เรื่อยๆ จะ update password ให้ถ้า user มีอยู่แล้ว):

```bash
cd qa-brain/backend
source .venv/bin/activate
```
ถ้ายังไม่มี `.venv`: `python3 -m venv .venv && pip install -r requirements.txt`
```bash
python -m scripts.seed_user qa@extosoft.com --password Test1234! --role qa_engineer
```

## 3. Start Backend

เลือก `<PORT>` ตามผลจาก step 0 (เช่น `8000` หรือ `8010`):

```bash
cd qa-brain/backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port <PORT>
```

เช็คว่าใช้ได้: `curl http://localhost:<PORT>/openapi.json` ต้องได้ JSON กลับมา ไม่ใช่ error page

## 4. Start Frontend

**ระวัง:** ถ้าจะ copy คำสั่งไปวางใน terminal ทีละหลายบรรทัด **อย่าใส่ comment ต่อท้ายบรรทัดเดียวกับคำสั่ง** (เช่น `npm install # ครั้งแรก`) — บาง shell (เช่น zsh บางค่า config) ไม่ตัด comment ออกให้ ทำให้ `#` หลุดเข้าไปเป็น argument จริงแล้ว error `EINVALIDTAGNAME` คำสั่งด้านล่างนี้จึงไม่มี inline comment แล้ว รันทีละบรรทัดได้เลย

ครั้งแรกครั้งเดียว ให้ติดตั้ง dependency ก่อน:
```bash
cd qa-brain/frontend
npm install
```

ถ้า backend อยู่ที่ port `8000` (ค่า default ไม่ต้องตั้งอะไรเพิ่ม):
```bash
npm run dev
```

ถ้า backend อยู่ที่ port อื่น (เช่น `8010`) ต้องบอก frontend ด้วย:
```bash
VITE_API_URL=http://localhost:8010 VITE_WS_URL=ws://localhost:8010 npm run dev
```

**เปิดเบราว์เซอร์ไปที่ URL ที่ vite แสดงจริง** (ดูบรรทัด `Local:` ใน output — ถ้ามี process อื่นค้างอยู่ vite จะขึ้นเป็น `5174` ไม่ใช่ `5173` เสมอไป อย่าเปิด `5173` ทื่อๆ ตาม habit ถ้า output บอกว่าเป็นเลขอื่น)

## 5. Login

- Email: `qa@extosoft.com`
- Password: `Test1234!`

(หรือ email/password ที่สร้างเองจาก step 2)

## 6. เริ่มใช้งาน

พิมพ์คำสั่งในแชทตาม [usage-guide.md](usage-guide.md) — เช่น:
```
Explore http://localhost:5173/login and generate a script
```
(แก้ port ในตัวอย่างให้ตรงกับที่ frontend รันจริงตาม step 4)

---

## Troubleshooting

| อาการ | สาเหตุที่เป็นไปได้ | วิธีแก้ |
|---|---|---|
| `curl .../openapi.json` ได้ `403 Blocked request` | port ชนกับโปรแกรมอื่น (พบบนเครื่องนี้ว่าเป็น OrbStack/Kong) | เปลี่ยนไปใช้ port อื่น (step 0) |
| `npm error EINVALIDTAGNAME` ตอน `npm install` | มี `#comment` ต่อท้ายบรรทัดคำสั่งเดียวกัน แล้ว shell ไม่ตัดออกให้ | แยก comment ไปคนละบรรทัด อย่าใส่ต่อท้ายคำสั่ง |
| Login วนซ้ำๆ ไม่จบ / กดอะไรก็เหมือนไม่ทำงาน | เปิด browser ผิด instance — มักเกิดจากมี `npm run dev` เก่าค้างอยู่ที่ port 5173 ทำให้ตัวใหม่ไป bump เป็น 5174 แต่ยังเปิด 5173 (ของเก่า) อยู่ | รัน step -1 เพื่อเช็ค/kill process เก่า แล้วเปิด URL ที่ vite แสดงจริงในรอบล่าสุด |
| Login ไม่ผ่าน (401/403 จาก `/auth/login`) | ยังไม่ได้ seed user หรือรหัสผ่านผิด | รัน step 2 ใหม่ |
| แชทไม่ตอบ/ค้าง | backend ไม่ได้รัน หรือ frontend ชี้ผิด port | เช็ค `VITE_API_URL`/`VITE_WS_URL` ตรงกับ port ที่ backend รันจริง |
| Qwen call error/timeout | endpoint ไม่เสถียร (รู้อยู่แล้ว) — มี fallback อัตโนมัติแล้ว | รอ fallback (~16 วินาที) หรือพิมพ์คำสั่งเดิมซ้ำ |
| ต้องการ AI จริงจาก Claude (7 tools ที่เหลือ) | `ANTHROPIC_API_KEY` ใน `.env` ยังเป็น placeholder | ใส่ key จริง หรือปล่อย `MOCK_MODE=true` ไว้เพื่อ demo แบบ mock |
