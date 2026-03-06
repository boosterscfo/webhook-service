# Report Generator Agent Memory

## Project Context

- **Project**: webhook-service (FastAPI + multiple job integrations)
- **PDCA Focus**: Completion reports after gap analysis passes threshold (≥90%)
- **Current Feature**: amazon-researcher (Slack-integrated ingredient analyzer)

## Report Generation Patterns

### Document Structure

PDCA completion reports follow this hierarchy:

1. **Executive Summary** - High-level results, match rate, overall status
2. **PDCA Cycle Overview** - Detail each phase (Plan, Design, Do, Check)
3. **Implementation Summary** - Files, LOC, decisions made
4. **Quality Metrics** - Design compliance, gap analysis results
5. **Architecture Decisions** - Rationale for key choices
6. **Key Learnings** - Retrospective (What went well, needs improvement, try next)
7. **Recommendations** - Actionable next steps
8. **Appendices** - Detailed gap analysis, risk assessment

### Key Sections to Include

**When match rate is 98%+**:
- Emphasize that it exceeded 90% threshold (no iteration needed)
- Highlight improvements over design (not deviations)
- Classify minor gaps as enhancements, not issues
- Recommend extraction of message constants as optional future work

**Architecture section should cover**:
- Why chosen pattern (e.g., "subpackage vs standalone")
- Alternatives considered + rejection reasoning
- Evidence/impact of decision
- Related design patterns used

**Learnings section**:
- Keep: Positive outcomes to replicate
- Problem: What went suboptimally + why + impact
- Try: Specific actionable improvements (TDD, smaller PRs, etc.)

### Integration Points

**Must cross-reference**:
- Plan document location: `docs/01-plan/features/{feature}.plan.md`
- Design document: `docs/02-design/features/{feature}.design.md`
- Analysis document: `docs/03-analysis/{feature}.analysis.md`
- All documents linked from report

**Report output path**:
- Primary: `docs/04-report/{feature}.report.md`
- Alternative: `docs/04-report/features/{feature}.report.md` (for organized folder structure)

### Data to Extract from Analysis

From the gap analysis document, pull:
- Match rate percentage and breakdown by category
- Critical/major/minor gap counts
- Severity classification with examples
- Implementation improvements (items in analysis "Added Features" section)
- Recommended updates to design doc

### Quality Metrics

**Standard checklist**:
- File structure: count files, confirm 100% match
- Data models: count fields, confirm match
- Service interfaces: method signatures, parameters
- Error handling: all scenarios covered?
- Main.py integration: clean, no side effects?

**Display as table**:
```
| Category | Items | Matches | Score |
| File Structure | 12 | 12 | 100% |
```

## Report Content Patterns

### ExecutiveSummary Format

- Quick status (Complete/Partial/Cancelled)
- Metrics snapshot (98%, 0 critical, 5 minor)
- Results box with completion rates

### Learnings (Keep/Problem/Try)

**Keep examples**:
- Design-driven development reduced surprises
- Type system caught errors early
- Clear separation of concerns paid off

**Problem examples**:
- Message constants left as inline strings (design said constants)
- Tests not written (no test req in design, but should have been)
- Documentation comments sparse (focused on correctness first)

**Try examples**:
- TDD: write tests before implementation
- Smaller PRs: easier review, better history
- Pre-implementation checklist: env vars, credentials, edge cases

## Async/Integration Patterns

For features with async code:
- Document concurrency strategy (Semaphore, asyncio patterns)
- Explain rate limiting decisions
- Note error recovery at each level (service, batch, orchestrator)
- Mention timeout and polling defaults

For Slack integrations:
- Note 3-second timeout constraint (Background Tasks required)
- Document message_url vs files.upload API differences
- Mention guard clauses for missing credentials

## Common Gaps & How to Present Them

### Minor Gap: Constants Location
- Design said: "Define constants in service module"
- Impl did: "Use inline strings in orchestrator"
- Present as: Functionally equivalent, clearer flow, could extract if needed
- Recommendation: Extract as optional phase 3 improvement

### Minor Gap: Constructor DI
- Design said: "Use global settings import"
- Impl did: "Pass as constructor parameters"
- Present as: Improvement for testability, better design pattern
- Update recommendation: Document improved pattern

### Minor Gap: Excel/Message Formatting
- Design said: "Use hyphen `-`"
- Impl did: "Use em dash `--`"
- Present as: Cosmetic, intentional for visual polish
- Recommendation: Update design doc to reflect standard

## Checkpoint Patterns

Before finalizing report:
- [ ] Match rate clearly stated with % and items
- [ ] All gaps classified (Critical=0, Major=0, Minor=N)
- [ ] Gap details in appendix with severity
- [ ] All 8 FRs (or feature-specific count) listed as Complete/Deferred
- [ ] File count: match implementation summary
- [ ] Links to plan/design/analysis documents work (relative paths)
- [ ] Next steps actionable (2-3 weeks effort estimate)
- [ ] Learnings section has both retrospective AND forward-looking

## File Paths in webhook-service

Key locations to reference:
- Main code: `amz_researcher/` subpackage
- Config: `app/config.py` (where env vars go)
- Entry point: `main.py` (where router included)
- External services: `browse_ai.py`, `gemini.py`, `analyzer.py`, `excel_builder.py`, `slack_sender.py`
- Orchestration: `orchestrator.py` (main pipeline)
- Endpoints: `router.py` (`/slack/amz` and `/research`)
