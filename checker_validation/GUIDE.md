# Reading guide: what does each generated report SAY?

60 short reports written by language models (C01 to C60). For each one, record **what the report
states**, not whether it is true. You do not know the patient, the model or its input, on purpose.
Takes about 45 to 60 minutes. Fill the "Labels" tab; use the dropdowns.

## The four findings

| Column | Choose | Notes |
|---|---|---|
| Type | not stated / adenocarcinoma / mucinous / signet-ring | "Mucinous adenocarcinoma" = mucinous. "Adenocarcinoma with a mucinous component" or "focal mucinous features" = adenocarcinoma (WHO: mucinous means more than 50% mucin). "Not mucinous" = adenocarcinoma. A confidence number such as "(model confidence 40%)" is NOT a mucin percentage. |
| Grade | not stated / G1 to G4 | well = G1, moderately = G2, poorly = G3, undifferentiated = G4. "Low grade" alone = not stated (it merges G1 and G2). "Grade cannot be determined" = not stated. |
| pT | not stated / pT1 to pT4 | Words count: "invades the muscularis propria" = pT2; "through the muscularis propria into pericolorectal/subserosal tissue" = pT3; "submucosa" = pT1; "visceral peritoneum" or "adjacent organ" = pT4. pT4a/pT4b = pT4. |
| Node | not stated / cannot be assessed / negative / positive | "Cannot be assessed" = the report says node status cannot be determined from this tissue. |
| Node hedged | yes / no | Only if Node is negative or positive: yes if the node statement is softened ("likely", "estimated", "predicted", "may", "model confidence"). Leave blank otherwise. |

If a report states two different values for one finding, pick the one stated as the diagnosis and
write the conflict in Notes.

## Extra claims (anything beyond the four findings)

Put **yes** in a column if the report makes that claim at all, positive or negative
("margins are free" is a margin claim). Leave blank if not.

| Column | Examples |
|---|---|
| LVI | lymphovascular, venous, vascular invasion; L0/L1, V0/V1 |
| Margins | margins free/involved, R0/R1 |
| Node count | "0 of 15 lymph nodes", "3/12 nodes" |
| pN | pN0, pN1, N2 |
| Size | "4.5 cm", "30 mm" |
| Distant met / M | pM1, M0, liver metastasis |
| MSI/MMR | MSI, MSS, mismatch repair, MLH1 |
| Perineural | perineural invasion |
| Budding | tumour budding |
| Other staging | Dukes, AJCC stage, stage II |
| Treatment | neoadjuvant, treatment effect, regression grade |
| Site | where in the bowel the tumour is: caecum, ascending, transverse, descending or sigmoid colon, hepatic/splenic flexure, rectosigmoid, rectum. "Colon" or "colorectal" alone does not count. |

**Other claim**: free text for any other factual claim about THIS patient's tissue that none of the
columns covers (for example necrosis, a polyp, ulceration). Leave blank if none.

## Rules

- Record what is written, even if it looks wrong or contradicts itself.
- Do not open `checker_validation/key/` until your sheet is finished.
- When unsure, pick your best answer and write why in Notes.
