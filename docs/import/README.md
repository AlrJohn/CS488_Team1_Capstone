# OneDrive import record

Snapshot: October 13, 2026. The recursive inventory contains **59 source files**.

- **51 files are included in the repository:** 46 unchanged originals and 5 copies with contact details removed from content or review metadata.
- **8 original videos remain in OneDrive**, with individual links in the [video index](../../media/videos/README.md).
- The original filenames are preserved. Files are grouped by purpose, and the original OneDrive path for each file is recorded in [file-manifest.json](file-manifest.json).

The two copies with visible contact details removed are [Team 1 Contract](../team/Team%201%20Contract.docx) and [Scrum Log 2](../meetings/scrum/ScrumLog2_Team1.docx). Only phone numbers, email addresses, their mailto targets, and any stored document thumbnail were removed. The local source downloads retain the originals. Email addresses were also removed from review metadata in the [September presentation](../../presentations/9_20%20Team%201%20Progress%20Presentation%20Report.pptx), [October presentation](../../presentations/Module%202%20Progress%20Report%20Team%201.pptx), and [software design](../design/Software%20and%20Defect%20Requirements.docx). These three files retain identical visible content, comment text, slide/document XML, and media. The manifest records separate hashes and changed metadata parts for all five public copies.

OneDrive's `Module3_Development and Testing` and `Module4_Deployment and Presentation` folders were empty. No implementation, test results, or deployment deliverables were available from those folders. Git does not track empty directories, so their state is recorded here rather than represented as completed project sections.

The nine files from `Module2_Design and Planning/Old Design` are retained in the [design archive](../../archive/old-design/README.md). The similarly named September 4 transcripts and the two research portfolios are distinct source files and were kept separately.

The manifest includes original paths, authenticated OneDrive URLs, source modification times and sizes, source QuickXor hashes, published paths, SHA-256 hashes of downloaded and published files, and any redaction. It contains no temporary download URLs or login tokens.

For future updates, put current requirements/design documents in their existing sections, retain superseded designs with their context, and update the section README and manifest when importing a new snapshot. Source dates describe the imported versions, so later edits in OneDrive are not automatically reflected here.
