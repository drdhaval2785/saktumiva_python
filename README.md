# saktumiva_python

1. Render manuscript tagged in saktumive TEI. 
2. Various tags in XML will be displayed with different markups in HTML for visual comparision as the work progresses.

Currently it is not collating the data as in saktumiva site.

`python tei_to_manuscript_html.py ../abhidhanachintamani_commentaries/charitrasimha/transcriptions/LDII_85885.xml output.html`

## Facsimile-style rendering

`tei_to_manuscript_html_2.py` lays the transcription out like the physical manuscript: one paper leaf per `<pb>`, one row per `<lb>`, ruled borders, marginal / top / bottom notes in the margins, supralinear and infralinear additions above / below the line, and editorial markup in a switchable colour layer. Each folio links to its page in the facsimile PDF.

`python tei_to_manuscript_html_2.py ../abhidhanachintamani_commentaries/charitrasimha/transcriptions/LDII_85885.xml output_2.html`

Options: `--pages 0001_2,0010_1-0012_2` renders only some folio sides; `--pdf PATH` / `--no-pdf` controls the facsimile link (by default `LDII_85885.pdf` is looked up in parent folders).
