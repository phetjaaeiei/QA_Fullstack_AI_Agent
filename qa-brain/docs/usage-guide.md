# QA Brain — คู่มือการใช้งาน

**อัปเดตล่าสุด:** 2026-07-04
**ดูแบบมี UI สวยกว่านี้ได้ที่:** https://claude.ai/code/artifact/946949eb-c9d4-43ab-885a-693ec5296180

พิมพ์ข้อความในแชทของ QA Brain ตามตัวอย่างด้านล่าง ระบบจะเลือก Agent และเครื่องมือที่เหมาะสมให้อัตโนมัติ ไม่ต้องเลือกเมนูเอง

**Legend:** 🟠 Claude (ต้องมี ANTHROPIC_API_KEY จริง หรือใช้ MOCK_MODE) · 🔵 Qwen 3.7 (ใช้งานได้จริงตอนนี้ ผ่าน DashScope)

---

## Automation QA Agent (9 tools)

> **หมายเหตุ:** Qwen 3.7 endpoint ที่ใช้อยู่ตอนนี้ไม่เสถียร 100% (ยืนยันแล้วว่ามีโอกาส fail แบบสุ่มแม้ request เดิมเป๊ะ) ถ้าเจอ error ให้ลองพิมพ์คำสั่งเดิมซ้ำอีกครั้ง ระบบตั้ง retry ไว้ 4 รอบอัตโนมัติแล้วแต่ไม่การันตี 100%

### 🔵 สำรวจแอปจริง แล้ว generate script
คำสั่งที่จับ: `explore`, `crawl`, `สำรวจ` + URL

```
Explore http://localhost:5173/login and generate a script
```

เปิด headless browser จริง สำรวจหน้าเว็บ (สูงสุด 5 หน้า, same-origin เท่านั้น) แล้วให้ Qwen เขียน Playwright script จาก element ที่เจอจริง — ขึ้น Scripts panel พร้อม label **🔍 Explored from live app**

### 🔵 สร้าง Script จาก OpenAPI Spec
คำสั่งที่จับ: `api spec`, `openapi`, `swagger` + URL

```
Generate a playwright script from this openapi spec http://localhost:8000/openapi.json
```

ดึง endpoint list จริงจาก spec แล้วให้ Qwen สร้าง test script — label **📄 From API spec**

### 🔵 สร้าง Script จาก Jira Story
คำสั่งที่จับ: `generate script`, `automation script`, `playwright`, `robot framework` + Story ID

```
Generate playwright script for PROJ-123
```

label **🎫 PROJ-123** ใน Scripts panel

### 🟠 ปรับ Script ตาม Company Standard
คำสั่งที่จับ: `company standard`, `house style`, `apply framework`

```
Apply company standard to this script:
​```
test('x', async () => {});
​```
```

จัดรูปแบบตามมาตรฐานใน `docs/automation-standards.md` (มีเนื้อหาจริงแล้ว)

### 🟠 แนะนำ Locator ทดแทนเมื่อ Element หาไม่เจอ
คำสั่งที่จับ: `locator`, `self-heal`, `element not found` + URL

```
this locator is broken: #submit-1, element not found at https://example.com/checkout
```

### 🟠 วิเคราะห์สาเหตุ CI Failure
คำสั่งที่จับ: `why fail`, `root cause` + GitHub Actions run URL

```
why did this fail? https://github.com/acme/repo/actions/runs/123456
```

แยกสาเหตุเป็น Bug / Data / Env / Script

### 🟠 Auto-fix Script ที่พัง
คำสั่งที่จับ: `fix script`, `auto fix`, `แก้ script`

```
auto fix this script:
​```
broken code here
​```
TimeoutError: locator not found
```

### 🟠 สร้าง Test Data
คำสั่งที่จับ: `test data`, `boundary data`

```
generate test data for the email field
```

### 🟠 เช็ค Script ครอบคลุม Story ไหม
คำสั่งที่จับ: `map script`, `script traceability` + Story ID

```
map script traceability for PROJ-123:
​```
test('reset password', async () => {});
​```
```

---

## Manual QA Agent — Claude sonnet-4-6 (5 tools)

| ต้องการ | พิมพ์ |
|---|---|
| สร้าง test case จาก story | `Generate test cases for PROJ-123` |
| วิเคราะห์ story หาจุดคลุมเครือ | `Analyze story PROJ-123 for missing requirements` |
| ดู traceability map | `Show traceability for PROJ-123 PROJ-124` |
| คำนวณ Release Readiness Score | `What's the release score for SPRINT-1` |
| หา coverage gap | `Find coverage gaps in SPRINT-1` |

---

## Security QA Agent — Claude opus-4-8 (7 tools)

| ต้องการ | พิมพ์ |
|---|---|
| สร้าง OWASP test case | `Generate OWASP test cases for PROJ-123` |
| Map story กับหมวด OWASP | `Map PROJ-123 to owasp categories` |
| สร้าง RBAC test matrix | `Generate RBAC matrix for admin and user roles on settings page` |
| สร้าง API security checklist | `Generate api security checklist for https://.../openapi.json` |
| จัดลำดับความเสี่ยงจากผล scan | วางผล scan JSON ในข้อความ + `triage vulnerabilities` |
| เขียน security defect | อธิบาย finding + `write security defect` |
| ดู OWASP coverage dashboard | `Show owasp dashboard for SPRINT-1` |

---

## เทคนิคการใช้ให้ได้ผลดี

- **URL ต้องมีช่องว่างคั่นทั้งสองด้าน** — ห้ามมีวรรคตอนต่อท้ายติดกัน (เช่น "...app." มีจุด) ระบบจะจับจุดนั้นเข้าไปในตัว URL ด้วย
- **ถ้าคำสั่งมี keyword แต่ไม่มี URL ที่ต้องใช้** — ระบบจะตอบ "ไม่เข้าใจ request" แทนที่จะ error หรือเงียบ ให้เติม URL แล้วพิมพ์ใหม่
- **Refresh หน้าเว็บได้ตามสบาย** — script/test case ที่ generate แล้ว persist ลง database จริง ไม่หายเมื่อ refresh
- **ถ้า Qwen call ไม่สำเร็จ** — พิมพ์คำสั่งเดิมซ้ำอีกครั้ง (endpoint ยังไม่เสถียร 100%)

---

**สถานะรวม:** Automation QA 9/9 tools ใช้งานได้ (2 บน Qwen 3.7, 7 บน Claude) · Manual QA Phase 1 ครบ · Security QA Phase 2 ครบ · Performance QA อยู่ระหว่าง review ยังไม่ merge เข้า main
