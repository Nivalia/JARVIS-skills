---
name: alert-manager
description: 'SEO alert manager: configure monitoring alerts for ranking drops, traffic changes, technical SEO issues, and competitor movements with severity thresholds. Part of a 20-skill SEO & GEO workflow suite. SEO预警/排名监控/流量异常/SEO工具/网站监控'
version: "6.0.0"
license: Apache-2.0
compatibility: "Claude Code ≥1.0, skills.sh marketplace, ClawHub marketplace, Vercel Labs skills ecosystem. No system packages required. Optional: MCP network access for SEO tool integrations."
homepage: "https://github.com/aaron-he-zhu/seo-geo-claude-skills"
when_to_use: "Use when setting up monitoring alerts for rankings, traffic, backlinks, technical issues, or AI visibility changes."
argument-hint: "<domain> [metric]"
metadata:
  author: aaron-he-zhu
  version: "6.0.0"
  geo-relevance: "low"
  tags:
    - seo
    - geo
    - seo-alerts
    - ranking-alerts
    - traffic-monitoring
    - competitor-alerts
    - automated-monitoring
    - anomaly-detection
    - SEO预警
    - SEOアラート
    - SEO알림
    - alertas-seo
  triggers:
    # EN-formal
    - "set up SEO alerts"
    - "monitor rankings"
    - "ranking notifications"
    - "traffic alerts"
    - "competitor alerts"
    - "automated monitoring"
    # EN-casual
    - "notify me when rankings drop"
    - "alert me if rankings drop"
    - "notify me of traffic changes"
    - "watch competitor changes"
    - "watch my keywords for changes"
    - "alert me about changes"
    # EN-question
    - "how to monitor my rankings"
    - "how to set up SEO alerts"
    # ZH-pro
    - "SEO预警"
    - "排名监控"
    - "流量报警"
    - "竞品变动提醒"
    # ZH-casual
    - "排名掉了提醒我"
    - "流量异常"
    - "有变化通知我"
    # JA
    - "SEOアラート"
    - "ランキング監視"
    # KO
    - "SEO 알림"
    - "순위 모니터링"
    # ES
    - "alertas SEO"
    - "monitoreo de rankings"
    # PT
    - "alertas de SEO"
    # Misspellings
    - "SEO allerts"
---

# Alert Manager

**Never be blindsided by a ranking drop or traffic crash again** — this skill configures the full SEO alert stack: ranking thresholds, traffic anomaly detection, technical health monitors, competitor movement alerts, and AI visibility watchers, each with a ready-made response plan.

**How to start**: `Set up SEO monitoring alerts for [domain]` or `Create ranking drop alerts for my top 20 keywords`

**System role**: Monitoring layer skill. It turns performance changes into deltas, alerts, and next actions.

> **[SEO & GEO Skills Library](https://github.com/aaron-he-zhu/seo-geo-claude-skills)** · 20 skills for SEO + GEO · [ClawHub](https://clawhub.ai/u/aaron-he-zhu) · [skills.sh](https://skills.sh/aaron-he-zhu/seo-geo-claude-skills)

## When This Must Trigger

Use this when the conversation involves any of these situations — even if the user does not use SEO terminology:

Use this whenever the task needs time-aware change detection, escalation, or stakeholder-ready visibility.

- Setting up SEO monitoring systems
- Creating ranking drop alerts
- Monitoring technical SEO health
- Tracking competitor movements
- Alerting on content performance changes
- Monitoring GEO/AI visibility changes
- Setting up brand mention alerts

## What This Skill Does

1. **Alert Configuration**: Sets up custom alert thresholds
2. **Multi-Metric Monitoring**: Tracks rankings, traffic, technical issues
3. **Threshold Management**: Defines when alerts trigger
4. **Priority Classification**: Categorizes alerts by severity
5. **Notification Setup**: Configures how alerts are delivered
6. **Alert Response Plans**: Creates action plans for each alert type
7. **Alert History**: Tracks alert patterns over time

## Quick Start

Start with one of these prompts. Finish with a short handoff summary using the repository format in [Skill Contract](https://github.com/aaron-he-zhu/seo-geo-claude-skills/blob/main/references/skill-contract.md).

### Set Up Alerts

```
Set up SEO monitoring alerts for [domain]
```

```
Create ranking drop alerts for my top 20 keywords
```

### Configure Specific Alerts

```
Alert me when [specific condition]
```

```
Set up competitor monitoring for [competitor domains]
```

### Review Alert System

```
Review and optimize my current SEO alerts
```

## Skill Contract

**Expected output**: a delta summary, alert/report output, and a short handoff summary ready for `memory/monitoring/`.

- **Reads**: current metrics, previous baselines, alert thresholds, and reporting context from [CLAUDE.md](https://github.com/aaron-he-zhu/seo-geo-claude-skills/blob/main/CLAUDE.md) and the shared [State Model](https://github.com/aaron-he-zhu/seo-geo-claude-skills/blob/main/references/state-model.md) when available.
- **Writes**: a user-facing monitoring deliverable plus a reusable summary that can be stored under `memory/monitoring/`.
- **Promotes**: significant changes, confirmed anomalies, and follow-up actions to `memory/open-loops.md` and `memory/decisions.md`.
- **Next handoff**: use the `Next Best Skill` below when a change needs action.

## Data Sources

> **Note:** All integrations are optional. This skill works without any API keys — users provide data manually when no tools are connected.

> See [CONNECTORS.md](https://github.com/aaron-he-zhu/seo-geo-claude-skills/blob/main/CONNECTORS.md) for tool category placeholders.

**With ~~SEO tool + ~~search console + ~~web crawler connected:**
Automatically monitor real-time metric feeds for ranking changes via ~~SEO tool API, indexing and coverage alerts from ~~search console, and technical health alerts from ~~web crawler. Set up automated threshold-based alerts with notification delivery.

**With manual data only:**
Ask the user to provide:
1. Current baseline metrics for alert thresholds (rankings, traffic, backlinks)
2. Critical keywords or pages to monitor
3. Alert priority levels and notification preferences
4. Historical data to understand normal fluctuation ranges
5. Manual reporting on metric changes when they check their tools

Proceed with the alert configuration using provided parameters. User will need to manually check metrics and report changes for alert triggers.

## Instructions

When a user requests alert setup:

1. **Define Alert Categories**

   ```markdown
   ## SEO Alert System Configuration
   
   **Domain**: [domain]
   **Configured Date**: [date]
   
   ### Alert Categories
   
   | Category | Description | Typical Urgency |
   |----------|-------------|-----------------|
   | Ranking Alerts | Keyword position changes | Medium-High |
   | Traffic Alerts | Organic traffic fluctuations | High |
   | Technical Alerts | Site health issues | Critical |
   | Backlink Alerts | Link profile changes | Medium |
   | Competitor Alerts | Competitor movements | Low-Medium |
   | GEO Alerts | AI visibility changes | Medium |
   | Brand Alerts | Brand mentions and reputation | Medium |
   ```

2. **Configure Alert Rules by Category**

   For each relevant category (Rankings, Traffic, Technical, Backlinks, Competitors, GEO/AI, Brand), define alert name, trigger condition, threshold, and priority level.

   > **Reference**: See [references/alert-configuration-templates.md](https://github.com/aaron-he-zhu/seo-geo-claude-skills/blob/main/monitor/alert-manager/references/alert-configuration-templates.md) for complete alert tables, threshold examples, and response plan templates for all 7 categories.

3. **Define Alert Response Plans**

   Map each priority level (Critical, High, Medium, Low) to a response time and immediate action steps.

4. **Set Up Alert Delivery**

   Configure notification channels (Email, SMS, Slack), recipient routing by role, suppression rules (duplicate cooldown, maintenance windows), and escalation paths.

5. **Create Alert Summary**

    ```markdown
    # SEO Alert System Summary
    
    **Domain**: [domain]
    **Configured**: [date]
    **Total Active Alerts**: [X]
    
    ## Alert Count by Category
    
    | Category | Critical | High | Medium | Low | Total |
    |----------|----------|------|--------|-----|-------|
    | Rankings | [X] | [X] | [X] | [X] | [X] |
    | Traffic | [X] | [X] | [X] | [X] | [X] |
    | Technical | [X] | [X] | [X] | [X] | [X] |
    | Backlinks | [X] | [X] | [X] | [X] | [X] |
    | Competitors | [X] | [X] | [X] | [X] | [X] |
    | GEO | [X] | [X] | [X] | [X] | [X] |
    | **Total** | **[X]** | **[X]** | **[X]** | **[X]** | **[X]** |
    
    ## Quick Reference
    
    ### If You Get a Critical Alert
    
    1. Don't panic
    2. Check alert details
    3. Follow response plan
    4. Document actions taken
    5. Update stakeholders
    
    ### Weekly Alert Review Checklist
    
    - [ ] Review all alerts triggered
    - [ ] Identify patterns
    - [ ] Adjust thresholds if needed
    - [ ] Update response plans
    - [ ] Clean up false positives
    ```

## Validation Checkpoints

### Input Validation
- [ ] Alert thresholds are based on realistic baseline data
- [ ] Critical keywords and pages clearly identified
- [ ] Response plans defined for each alert priority level
- [ ] Notification channels configured with appropriate recipients

### Output Validation
- [ ] Every metric cites its data source and collection date
- [ ] Alert thresholds account for normal metric fluctuations
- [ ] Response plans are specific and time-bound
- [ ] Source of each alert trigger clearly stated (~~SEO tool API alert, ~~search console notification, ~~web crawler alert, or manual user check)

## Example

**User**: "Set up ranking drop alerts for my top keywords"

**Output**:

```markdown
## Ranking Alert Configuration

### Critical Keywords (Immediate Alert)

| Keyword | Current | Alert If | Priority |
|---------|---------|----------|----------|
| best project management software | 2 | Drops to 5+ | 🔴 Critical |
| project management tools | 4 | Drops to 8+ | 🔴 Critical |
| team collaboration software | 1 | Any drop | 🔴 Critical |

### Important Keywords (Same-Day Alert)

| Keyword | Current | Alert If | Priority |
|---------|---------|----------|----------|
| agile project management | 7 | Drops out of top 10 | 🔴 High |
| kanban software | 9 | Drops out of top 10 | 🔴 High |

### Alert Response Plan

**If Critical Keyword Drops**:
1. Check if page is still indexed (site:url)
2. Look for algorithm update announcements
3. Analyze what changed in SERP
4. Review competitor ranking changes
5. Check for technical issues on page
6. Create recovery action plan within 24 hours

**Notification**: Email + Slack to SEO team immediately
```

## Tips for Success

1. **Start simple** - Don't create too many alerts initially
2. **Tune thresholds** - Adjust based on normal fluctuations
3. **Avoid alert fatigue** - Too many alerts = ignored alerts
4. **Document response plans** - Know what to do when alerts fire
5. **Review regularly** - Alerts need maintenance as your SEO matures
6. **Include positive alerts** - Track wins, not just problems

## Alert Threshold Quick Reference

| Metric | Warning | Critical | Frequency |
|--------|---------|----------|-----------|
| Organic traffic | -15% WoW | -30% WoW | Daily |
| Keyword positions | >3 position drop | >5 position drop | Daily |
| Pages indexed | -5% change | -20% change | Weekly |
| Crawl errors | >10 new/day | >50 new/day | Daily |
| Core Web Vitals | "Needs Improvement" | "Poor" | Weekly |
| Backlinks lost | >5% in 1 week | >15% in 1 week | Weekly |
| AI citation loss | Any key query | >20% queries | Weekly |
| Security issues | Any detected | Any detected | Daily |

> **Reference**: See [references/alert-threshold-guide.md](https://github.com/aaron-he-zhu/seo-geo-claude-skills/blob/main/monitor/alert-manager/references/alert-threshold-guide.md) for baseline establishment, threshold setting methodology, fatigue prevention, escalation paths, and response playbooks.


### Save Results

After delivering monitoring data or reports to the user, ask:

> "Save these results for future sessions?"

If yes, write a dated summary to `memory/monitoring/YYYY-MM-DD-<topic>.md` containing:
- One-line headline finding or status change
- Top 3-5 actionable items
- Open loops or anomalies requiring follow-up
- Source data references

If any findings should influence ongoing strategy, recommend promoting key conclusions to `memory/hot-cache.md`.

## Reference Materials

- [Alert Threshold Guide](https://github.com/aaron-he-zhu/seo-geo-claude-skills/blob/main/monitor/alert-manager/references/alert-threshold-guide.md) — Recommended thresholds by metric, fatigue prevention strategies, and escalation path templates

## Next Best Skill

- **Primary**: [rank-tracker](https://github.com/aaron-he-zhu/seo-geo-claude-skills/blob/main/monitor/rank-tracker/SKILL.md) — pair alerts with a baseline measurement workflow.

## Related Skills in This Suite

| Phase | Skills |
|-------|--------|
| **Research** | [keyword-research](../../research/keyword-research/SKILL.md), [competitor-analysis](../../research/competitor-analysis/SKILL.md), [serp-analysis](../../research/serp-analysis/SKILL.md), [content-gap-analysis](../../research/content-gap-analysis/SKILL.md) |
| **Build** | [seo-content-writer](../../build/seo-content-writer/SKILL.md), [geo-content-optimizer](../../build/geo-content-optimizer/SKILL.md), [meta-tags-optimizer](../../build/meta-tags-optimizer/SKILL.md), [schema-markup-generator](../../build/schema-markup-generator/SKILL.md) |
| **Optimize** | [on-page-seo-auditor](../../optimize/on-page-seo-auditor/SKILL.md), [technical-seo-checker](../../optimize/technical-seo-checker/SKILL.md), [internal-linking-optimizer](../../optimize/internal-linking-optimizer/SKILL.md), [content-refresher](../../optimize/content-refresher/SKILL.md) |
| **Monitor** | [rank-tracker](../rank-tracker/SKILL.md), [backlink-analyzer](../backlink-analyzer/SKILL.md), [performance-reporter](../performance-reporter/SKILL.md), [alert-manager](../alert-manager/SKILL.md) |
| **Cross-cutting** | [content-quality-auditor](../../cross-cutting/content-quality-auditor/SKILL.md), [domain-authority-auditor](../../cross-cutting/domain-authority-auditor/SKILL.md), [entity-optimizer](../../cross-cutting/entity-optimizer/SKILL.md), [memory-management](../../cross-cutting/memory-management/SKILL.md) |

> **Install the full suite**: See [README](https://github.com/aaron-he-zhu/seo-geo-claude-skills) for one-command install of all 20 skills.
