GOLD LABELLING GUIDE (v2, 4 Oct) - TCGA colorectal pathology reports

WHAT YOU ARE DOING
You read 50 pathology reports and write down what each report SAYS, field by field. You are not judging
anything medically. Two people label the same 50 reports on their own. Afterwards we compare and settle the
differences. About 3 minutes per report.

BEFORE YOU START
- Read the "Cheat sheet" tab. It turns the words you will meet into drop-down options.
- Work alone. Do not talk about cases with the other person until you have both finished.
- Do not open structured_labels.json, gdc_clinical_coad_read.tsv or the other person's sheet.

READ THE PDF, NOT THE TEXT
Click the link in column C. The PDF is the original scan. You can try Cmd+F (Ctrl+F) inside the PDF
to search for a word; scans are not always searchable.
- A filled circle (black) on a form is the answer that was ticked. Empty circles are only options.
  An option printed on a form is NOT a finding unless it is ticked.
- Handwriting in the margin (like "Adenocarcinoma, NOS 8140/3") is a coder's note. Use it only if the typed
  report says nothing on that field.
- If the PDF is split into two files (part1 + part2), read both.

THE ONE RULE FOR "I CANNOT FIND IT"
Every yellow cell must be filled. An empty cell will be read as "forgot", so never leave one empty.
- The report does not mention it (you looked) -> choose "not stated". This is NOT the same as negative.
  Example: no word about margins -> margins = "not stated", not "clear".
- It is there, but the scan is too blurry or garbled to read, or a tick box has no visible tick ->
  choose "unreadable in the scan".
- Numbers (nodes positive / examined): if the report gives no number, leave the cell empty. This is the only
  case where empty is correct. Say "no node count" in Notes.
- Mucinous %: fill only if a percentage is written. Otherwise leave empty (empty is correct here).
- T2 columns: leave empty when the report has only one tumour (empty is correct here).
- Before you write "not stated", search the PDF once for the word (Cmd+F / Ctrl+F in the PDF, if it lets you search) and check
  the final diagnosis, the synoptic summary and the microscopic description.
- If you are unsure, pick your best answer, set Confidence to "unsure" and say why in Notes. Never guess
  silently.

MORE THAN ONE TUMOUR (like report G22)
Some reports describe two (or three) separate cancers in the bowel, for example "bifocal", "synchronous",
or "specimen 1 / specimen 2" with their own size, depth or stage.
1. Put the number of cancers in "How many tumours?" (1, 2 or 3).
2. T1 = the INDEX tumour. The index tumour is the one with the highest pT. If the pT is the same: the higher
   grade. If that is the same too: the larger one. If the report itself names a main tumour, use that one.
3. T2 = the other tumour. Fill T2 type, grade, pT and site. If there is a third tumour, put it in Notes.
4. If the report gives ONE combined diagnosis for both (for example "bifocal tumour, pT3 pN0"), put it in T1,
   set T2 to "not stated" where nothing separate is given, and write "combined diagnosis" in Notes.
5. The whole-case columns (pN, nodes, node status, lymphovascular invasion, margins, post-treatment) are ONE
   answer per report. If the nodes are counted separately for each specimen, write the index tumour's
   numbers and put the other numbers in Notes.
6. NOT a second tumour: different areas of the same tumour (for example part mucinous), a polyp or adenoma
   with no cancer, a tumour in another organ, metastases, or a cancer mentioned only as history.
   A tiny cancer inside a polyp elsewhere in the bowel IS a second tumour (its pT is pTis).
7. If the report gives two grades for ONE tumour ("moderately to poorly differentiated"), that is one tumour:
   choose the worse grade (G3) and say so in Notes.

THE REPORT CONTRADICTS ITSELF
Example: "pN2" in one place and "0/16 nodes negative" in another. Use the final diagnosis or the synoptic
summary, set Confidence to "unsure", and describe the conflict in Notes.

FIELD BY FIELD
Histologic type - the WHO rule: mucinous adenocarcinoma means more than 50% of the tumour is mucinous.
  "Mucinous adenocarcinoma" with no percentage -> mucinous adenocarcinoma (>50%).
  "with mucinous features / component / differentiation", "partially / focally mucinous", or a stated
  percentage of 50% or less -> adenocarcinoma with mucinous component.
  Signet-ring cell carcinoma follows the same >50% rule. "Signet-ring features" or "focal signet-ring cells"
  -> adenocarcinoma NOS (and mention it in Notes).
  Medullary, neuroendocrine, squamous and so on -> other carcinoma.
Mucinous % - only if a number is written.
Grade - well = G1, moderately = G2, poorly = G3, undifferentiated = G4. Two-level "low grade" / "high grade"
  -> the two-tier options (do not convert to G-numbers).
pT - only when a T code is written (pT3, T3, ypT3). T4a / T4b -> pT4. If only the depth is described and no T
  code is written, choose "not stated" and copy the depth words into Notes.
pN - as written. N1a / N1b / N1c -> pN1. N2a / N2b -> pN2.
Nodes positive / examined - the two numbers when given ("3/17" -> 3 and 17).
Node status - positive: any lymph node with cancer (count 1 or more, pN1 or pN2). For N1c (tumour deposits
  only) choose positive and write "N1c" in Notes. Negative: nodes were examined and none had cancer
  (0/n, pN0, "nodes negative"). Distant metastasis (liver, lung) does not count.
Lymphovascular invasion - present: lymphatic, vascular, venous or angiolymphatic invasion, or L1 / V1.
  absent: L0 and V0, or "no lymphovascular invasion". Perineural invasion is not lymphovascular.
Margins - involved: tumour at any cut edge (R1, R2, "margin positive"). clear: all edges free (R0). A close
  but clear margin is clear.
Tumour site - the most specific site given for the tumour (T1 site for the index tumour, T2 site for the
  other).
Post-treatment - yes if the report says ypTNM, neoadjuvant, treatment effect or tumour regression grade.
Confidence - sure / unsure, for the report as a whole.

ABOUT THE SHEET
- Orange headers = tumour 2. Blue = tumour 1. Grey = whole case.
- Row 3 (grey) is an invented worked example. Do not edit it.
- Put your name and the date in B1 and D1. Save often.
