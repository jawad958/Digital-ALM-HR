# Alpago HR — Demo Guide

## Starting up

Two terminals.

**Terminal 1 — API**
```powershell
cd C:\Users\Jawad\Desktop\alpago-hr\apps\api
.\.venv\Scripts\Activate.ps1
alembic upgrade head
python seed_demo.py          # wipes and reseeds all demo data
uvicorn alpago.main:app --reload
```

**Terminal 2 — Web**
```powershell
cd C:\Users\Jawad\Desktop\alpago-hr\apps\web
pnpm dev
```

Open http://localhost:3000

> Re-run `python seed_demo.py` any time to reset to a clean demo state. Stop the API first.

---

## Logins

**Password for every account: `Alpago@2026`**

| Email | Role | Use it to show |
|---|---|---|
| `jawad@alpagomanufacturing.com` | Admin + Head of HR | Everything — start here |
| `manager@alpagomanufacturing.com` | Department Manager | Raising a hiring request |
| `agm@alpagomanufacturing.com` | AGM | Approval step 1 |
| `gm@alpagomanufacturing.com` | GM | Approval step 2 |
| `ceo@alpagomanufacturing.com` | CEO | Final approval |
| `hr@alpagomanufacturing.com` | Head of HR | Offers, documents |
| `ta@alpagomanufacturing.com` | Talent Acquisition | Candidates, interviews |
| `pro@alpagomanufacturing.com` | PRO | Visas, Emirates ID |
| `it@alpagomanufacturing.com` | IT | Onboarding: accounts, laptop |
| `employee@alpagomanufacturing.com` | Employee | Self-service view |

Sign out via the icon next to the theme toggle, bottom-left.

---

## The 10-minute walkthrough

### 1. The problem (30 sec)
Open on the **Dashboard**. Frame it: today this runs on WhatsApp messages and phone
calls. Nobody can answer "where is that approval?" or "whose visa expires next month?"

### 2. Raise a hiring request — the approval chain (3 min)

Sign in as **manager@** → **Hiring** → **+ New hiring request**.

Fill in a real-sounding role (e.g. *Senior Safety Officer, Contracting, 2 positions,
AED 18,000–24,000*). Submit.

Go to **Approvals** → **All requests**. Point at the step cards: the request is now
sitting at **AGM**, and the chain ahead of it is visible — AGM → GM → CEO.

Now sign out, sign in as **agm@** → **Approvals** → the request is under
**Waiting on me** → **Approve**. Sign in as **gm@**, approve. Then **ceo@**, approve.

> **The point to make:** nobody chased anyone. Each approver saw only what needed
> their decision, and every step is time-stamped and attributed.

### 3. Candidates and AI screening (2 min)

Sign in as **ta@** → **Candidates**. Show the pipeline stages and the AI screening
scores already on file (Lina Nasser 82, Priya Sharma 88).

Upload a CV from `alpago-hr\sample-docs\` (`CV-Amira-Haddad.pdf`) to show intake.

> If your Claude API key is set (see below), the screening runs live against the job
> description. Without a key, the seeded scores still demonstrate the output.

### 4. Offer → employee (2 min)

**Offers** → the accepted offer for Priya Sharma. Show it went through its own
approval chain before it could be sent.

**Employees** → **Priya Sharma**. She exists because her offer was accepted.
Show the four tabs:
- **Profile** — full record: personal, employment, compensation, compliance, emergency contact
- **Onboarding** — the joining checklist split by owner: IT (email, system access),
  Assets (laptop, phone, access card), PRO (visa, medical, Emirates ID), HR, Finance.
  Tick one off live — the percentage moves.
- **Documents** — required-document checklist with a completeness bar, and what's missing
- **Activity** — every change, who made it, when

### 5. Compliance — the slide that lands (2 min)

**Documents**. Four numbers at the top: Expired, Expiring in 7 days, Expiring in
60 days, Awaiting verification.

> **The point to make:** this is the question that currently gets answered by someone
> going through a filing cabinet. An expired visa is a fine and a stopped project.

Click into the watchlist, sorted soonest-first. Click a row to jump to that person.

### 6. The audit trail (30 sec)

Any detail page → **Activity** tab. Or **Settings → Users & roles** to show the access
model and which roles are unfilled.

> **Closing line:** every action in this system is attributable. Nothing happens in a
> DM that nobody else can see.

---

## Adding your Claude API key

In `apps\api\.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Restart the API. This turns on:
- **Job description drafting** — tick "Draft the job description with AI" when creating a hiring request
- **CV screening** — scores and summarises a candidate against the JD on upload
- **Interview questions** — generates role-specific questions
- **Offer letter drafting** — produces the letter body from the offer terms

Everything else works without a key.

---

## If something breaks mid-demo

| Symptom | Fix |
|---|---|
| Page shows "Loading…" forever | API isn't running, or it crashed — check Terminal 1 |
| Bounced to the login screen | Token expired or cleared — sign in again |
| A list is empty that shouldn't be | Re-run `python seed_demo.py`, restart the API |
| Approval sits with nobody | **Settings → Users & roles** shows which roles have no holder |
| Styling looks wrong | Hard refresh with `Ctrl+Shift+R` |

**Safest recovery:** stop both terminals, re-run `python seed_demo.py`, start both again.
Takes about 30 seconds and puts you back to a known-good state.

---

## What is and isn't built

**Working end to end**
- Email/password login with JWT, ten roles
- Hiring requests with the AGM → GM → CEO approval chain, SLA tracking, escalation
- Candidates with stages, CV upload, AI screening
- Interviews with scheduling and scored evaluations
- Offers with their own approval chain, candidate accept link
- Employees with full profiles and the joining checklist (IT / assets / PRO / HR / Finance)
- Documents attached to any employee or candidate, with required-document checklists,
  expiry tracking and verification
- Audit trail across every module

**Not built yet**
- Email and WhatsApp notifications are written to the database but not actually sent
  (needs a Resend key and a WhatsApp Business number)
- Performance reviews, leave management, payroll
- Settings → Approval chains and Templates are still placeholder screens; chains are
  seeded in the database and editable there
- Employee self-service portal
