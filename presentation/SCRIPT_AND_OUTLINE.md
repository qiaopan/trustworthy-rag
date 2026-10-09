# Trustworthy RAG presentation storyboard and speaker notes

Target: 8--10 minutes total. The two speakers should each talk for roughly
4--5 minutes. This is a student-editable storyboard and rehearsal script, not
a substitute for checking every numerical claim against the locked result file.

## Slide plan

| Slide | Time | Speaker | On-slide content | Speaker note |
|---|---:|---|---|---|
| 1. Title and question | 0:00--0:35 | A | Title; one-sentence question | "RAG gives an LLM outside information, but that information can contain an instruction. We ask whether a RAG system can judge a retrieved passage before it reaches the generator." |
| 2. Why this matters | 0:35--1:20 | A | Diagram: user question to retriever to mixed trusted/untrusted context to LLM | "The attacker need not change the user's question. A malicious email, page, or document can be retrieved and compete with the user instruction." |
| 3. Existing approaches and gap | 1:20--2:10 | A | BIPIA benchmark; PIGuard detector; hard-filter trade-off | "A detector can remove suspicious text, but a hard filter can also remove the part that answers the question. This is the security--utility tension we measure." |
| 4. Hypothesis | 2:10--2:45 | A | Hypothesis and limited claim | "We hypothesised that relevance plus injection risk would retain more answer-bearing evidence than a detector-only rule while keeping attack risk low. We do not claim universal robustness." |
| 5. Methods | 2:45--3:55 | A | B0; B2 raw; B2-win; B3; Ours | "B0 is ordinary RAG. Raw B2 is original chunk-level PIGuard filtering. B2-win is our window-scoring ablation; B3 is stricter risk-only selection; Ours combines relevance and risk. Do not call B2-win the original baseline." |
| 6. Experimental design | 3:55--4:50 | B | 300 attacked + 20 clean; 15 families by 3 positions; metrics | "The primary test is stratified and frozen. The 100-case pilot is only an infrastructure check; the 45-case follow-up is supplementary and not pooled with the primary result." |
| 7. Results | 4:50--6:10 | B | Final locked table/plot; Wilson intervals | "Use only numbers from the final audit. Lead with the finding actually supported: how security measures and evidence retention move together. State if ASR differences are tied." |
| 8. What the ablation teaches | 6:10--7:00 | B | B2 raw vs B2-win vs B3 vs Ours | "The useful comparison is detector-only filtering versus relevance-aware selection. The conflict term was inert in this implementation, so we do not claim a gain from it." |
| 9. Limits | 7:00--7:45 | B | One generator; small clean set; constructed pool; model judge | "Our claims are bounded to BIPIA EmailQA. We substituted a Qwen judge for BIPIA's original GPT-3.5 and treat UNKNOWN outputs conservatively." |
| 10. Conclusion | 7:45--8:30 | B | One take-away; future work | "Security should be evaluated alongside retained useful evidence. Next we would test more models, more clean cases, adaptive attacks, and a validated conflict score." |

## Required result-slide checklist

- Use the locked Main-Test denominator: 300 attacked + 20 clean.
- Show B0, raw B2, B2-win, B3, and Ours separately.
- Label ASR, attack-context inclusion, answer-bearing retention, and clean
  results with denominators.
- Do not pool the 100-case pilot or 45-case follow-up into the graph.
- Add a footnote: "Qwen-72B judge replaces BIPIA's GPT-3.5; UNKNOWN counted
  as not successful."
- Put source/repository and BIPIA/PIGuard citations in small readable text.

## Recording checklist

1. Each speaker rehearses a 4--5 minute portion aloud.
2. Keep visuals sparse: one pipeline diagram, one method table, one results
   chart, and one limitations slide are more persuasive than dense text.
3. Record a playable MP4 of 8--10 minutes and watch the exported file once.
4. Revise wording to sound like the presenters' own voice; confirm every
   numerical statement against the final metric report before recording.
