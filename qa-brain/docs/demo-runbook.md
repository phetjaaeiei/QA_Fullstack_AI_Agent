# Automation QA Demo Runbook (Track A)

**Target app:** QA Brain เอง (dogfooding) — ไม่ต้องพึ่ง staging env ภายนอก
**อัปเดตล่าสุด:** 2026-07-04 — รันจริงผ่าน UI ทั้ง 2 module สำเร็จ, เจอและแก้บั๊กจริง 2 ตัวระหว่างทดสอบ (ดูรายละเอียดด้านล่าง)

**ดูคู่กับ:** [running-locally.md](running-locally.md) (วิธี start server ครบ + troubleshooting) และ [usage-guide.md](usage-guide.md) (คำสั่งแชททั้งหมดที่มี)

---

## Pre-flight (ทำก่อน demo วันจริง)

1. **เช็ค port ว่างก่อน** — บนเครื่อง dev พบว่า port `8000` โดน intercept โดย OrbStack/Kong routing ของ project อื่น (ไม่เกี่ยวกับ QA Brain) ทำให้ backend ตอบ `403 Blocked request` แทนที่จะเป็น response จริง
   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/openapi.json
   ```
   ถ้าไม่ได้ `200` ให้รัน backend บน port อื่นแทน (ตัวอย่างนี้ใช้ **8010**) แล้วตั้ง `VITE_API_URL`/`VITE_WS_URL` ให้ frontend ชี้ตาม — ดูรายละเอียดเต็มใน running-locally.md

2. **เช็คว่าไม่มี vite process ค้างซ้ำ** — เจอมาแล้วว่าถ้ามี `npm run dev` เก่าค้างอยู่ (ไม่ได้ kill ก่อนเปิดใหม่) ตัวใหม่จะ auto-bump ไป port ถัดไป (5174) โดยไม่รู้ตัว ทำให้เปิด browser ผิด instance แล้วดูเหมือน "กดปุ่มไม่ได้" (จริงๆ คือ CORS/connection ผิด port) เช็คก่อน demo:
   ```bash
   lsof -i :5173 -i :5174 2>/dev/null | grep LISTEN
   ```
   ควรเห็นแค่ port เดียว (5173) ถ้าเห็น 2 ตัว ให้ kill ทิ้งแล้วเปิดใหม่ให้เหลือตัวเดียว

3. **เช็ค MOCK_MODE / MOCK_QWEN** — ตอนนี้แยกกันแล้ว:
   - `MOCK_MODE=true` → Claude-based tools (Manual QA, Security QA, และ 7/9 tools ของ Automation QA) ยังเป็น mock เพราะ `ANTHROPIC_API_KEY` ยังเป็น placeholder
   - `MOCK_QWEN=false` (default) → **Module 01 กับ 02 เรียก Qwen 3.7 จริง** — ทั้ง crawl และ generate เป็นของจริงไม่ใช่ mock แล้ว

4. **Login credential** (สร้างไว้แล้วผ่าน `scripts/seed_user.py`):
   - Email: `qa@extosoft.com`
   - Password: `Test1234!`

5. **Start servers** — ดูคำสั่งเต็มใน [running-locally.md](running-locally.md)

---

## สิ่งที่ verify แล้วว่าทำงานจริง (ไม่ใช่แค่ mock)

ทดสอบจริงผ่าน UI จริง (คลิกปุ่มจริงด้วย Playwright, ไม่ใช่แค่เรียกฟังก์ชันตรงๆ) — 2026-07-04:

- **Module 01 (Explore)** — ยิงคำสั่งแชทจริง "Explore http://localhost:5173/login and generate a script" → crawl หน้า login จริง เจอ element ครบ 3 ตัว → ส่งให้ Qwen 3.7 จริง → ได้ Playwright script ที่ถูกต้อง อ้างอิง element จริงที่เจอ (`input[name="email"]`, `input[name="password"]`, ปุ่ม "Sign In") → ขึ้น Scripts panel พร้อม persist ผ่าน refresh ได้จริง
- **Module 02 (API Spec)** — ยิงคำสั่ง "Generate a playwright script from this openapi spec ..." → parse spec จริง 8 endpoints → Qwen สร้าง script จริง

## สคริปต์ Demo

1. Login: `qa@extosoft.com` / `Test1234!`

2. พิมพ์ในแชท:
   ```
   Generate a playwright script from this openapi spec http://localhost:8010/openapi.json
   ```
   **คาดหวัง:** เห็นข้อความ "Generating playwright script from API spec..." แล้ว script ปรากฏใน Scripts panel พร้อม label **"📄 From API spec"** — ใช้เวลาไม่กี่วินาที

3. พิมพ์ในแชท:
   ```
   Explore http://localhost:5173/login and generate a script
   ```
   **คาดหวัง:** เห็นข้อความ "กำลังสำรวจ..." **รอประมาณ 5–18 วินาที** (เปิด browser จริง + เรียก Qwen จริง) แล้ว "สำรวจและสร้าง script สำเร็จ" — script ที่สองปรากฏพร้อม label **"🔍 Explored from live app"**

4. **Refresh หน้าเว็บทั้งหมด** — script ทั้งสองตัวต้องยังอยู่ (persist ลง DB จริง)

## ข้อควรระวังระหว่าง Demo

- **Qwen ไม่เสถียร 100%** — endpoint มีโอกาส fail แบบสุ่ม (ยืนยันแล้วว่า request เดิมเป๊ะสำเร็จบ้างไม่สำเร็จบ้าง) ถ้า fail ระบบจะ **fallback เป็น `[MOCK]` script อัตโนมัติภายใน ~16 วินาที** แทนที่จะ error — ถ้าเกิดระหว่าง demo ให้บอกผู้ฟังตรงๆ ว่า "นี่คือ fallback ที่ระบบออกแบบไว้เผื่อ AI ตอบช้า" แทนที่จะเนียนว่าเป็นผลจริง (เช็คได้จากคำว่า `[MOCK]` ใน script content)
- URL ในข้อความแชทต้องมีช่องว่างคั่นทั้งสองด้าน ห้ามมีเครื่องหมายวรรคตอนต่อท้ายติดกัน
- ถ้าพิมพ์ "explore" หรือ "openapi" โดยไม่มี URL ระบบจะตอบ "ไม่เข้าใจ request..." แทนที่จะ error หรือเงียบ
- การ explore จำกัดไว้ที่ 5 หน้าและ same-origin link เท่านั้น

## บั๊กที่เจอและแก้แล้วระหว่างเตรียม demo (เก็บไว้กันเจอซ้ำ)

1. **"ปุ่ม Sign In กดไม่ได้"** — สาเหตุจริงคือ vite process ค้างซ้ำ 2 ตัว (5173 ถูกต้อง, 5174 ผิด env) ทำให้ browser บางครั้งไปเจอ instance ที่ชี้ backend ผิด port — วิธีเช็ค: ดู pre-flight ข้อ 2 ด้านบน
2. **"เชื่อมต่อไม่สำเร็จ" ขึ้นตอนเปิดแอปแม้ backend ทำงานปกติ** — React StrictMode (dev mode) mount component ซ้ำ ปิด WebSocket ตัวแรกก่อนเชื่อมต่อเสร็จ ทำให้ error message หลอกขึ้นมาทั้งที่การเชื่อมต่อจริงสำเร็จ — แก้แล้วใน `useAgentChat.ts` (ไม่กระทบ demo แล้ว)
