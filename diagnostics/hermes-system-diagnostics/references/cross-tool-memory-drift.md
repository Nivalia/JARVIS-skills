# Cross-Tool Memory Drift SOP

## The pattern

User has settings/persona/state configured in **another tool** (GPTs, Cursor, Claude Projects, old Hermes session, manual notes) and carries that belief into current Hermes session. Frequently observed shapes:

- "I already set up the JARVIS persona" → actually no, or in a different tool
- "Gateway is always running" → died 2h ago, no auto-restart
- "QQBot is enabled" → never configured in current install
- "Hermes version is X" → X was never published, or different package
- "I added the key to .env" → never added, or added with placeholder value

## SOP (apply before answering ANY user claim about config/state)

### Step 1: Identify the claim
Extract the exact assertion: *"Y is configured / running / set / version Z"*

### Step 2: Locate the source of truth (parallel grep)
Run independent greps in a single tool-call batch — don't serialize:

```bash
# Example: user claims "QQBot is configured"
grep -nE "(qqbot|QQBot|tencent)" /root/.hermes/config.yaml
grep -nE "^QQ|^QQBOT" /root/.hermes/.env | sed 's/=.*/=***/'
jq '.providers | keys' /root/.hermes/auth.json   # or python json.load if no jq
ls /root/.hermes/skills/ | wc -l
ps aux | grep -E "qqbot|gateway" | grep -v grep
```

### Step 3: Build the comparison table
| Source | User claim | Actual grep result | Verdict |
|---|---|---|---|
| config.yaml | "QQBot registered" | line 188-189: `qqbot: [hermes-qqbot]` | ✅ |
| .env | "all keys there" | 5 vars present, all non-placeholder | ✅ |
| auth.json | "qqbot provider set" | 0 hits in `.providers` | ❌ |
| Process list | "running" | no qqbot process | ❌ |

### Step 4: State the delta plainly, no face-saving
Don't round-corner the user's belief. Format:
- **确认对**: where grep matches user's claim
- **修正**: where it doesn't (cite line numbers, grep output)
- **下一步**: propose specific tool action to fix

### Step 5: Do not write the "fix" into memory as a fact about the user
If you fix it, write the **after-state** to memory, not "user was wrong about X". Memory hygiene rule: declarative facts about the system, not narrated corrections.

## Re-asking the same question in one session

If the user re-asks the same diagnostic question in the same session:
1. Verify the state hasn't changed (re-grep, quick check)
2. State: "状态与上一轮一致,没有变化"
3. List 2-3 likely reasons (UI didn't render, user is verifying my behavior, hot-reload needed)
4. Ask which one applies — don't repeat the full answer

## Anti-pattern: substituting memory for grep
If memory says "QQBot configured" but you didn't grep in this session, **grep before answering**. Memory can be wrong (decay, contamination from prior tools, session context lost). grep is free and authoritative.

## Anti-pattern: hiding the delta
Don't write "我看了一下,大部分配置都在" when 2 of 4 sources are empty. State each row's status explicitly. The user benefits from knowing exactly which piece is missing.