# Data

Raw data is **not** committed to this repo (see `.gitignore`). Download it yourself:

## GenoTEX benchmark (primary)
- Paper: arXiv:2406.15341
- Check the paper/repo for the current dataset download link and license terms
- Place downloaded files under `data/raw/genotex/` (gitignored)

## PBMC3k (sanity-check dataset)
- Standard 10x Genomics dataset, loadable directly via Scanpy:
```python
import scanpy as sc
adata = sc.datasets.pbmc3k()
```

## Notes
- Verify each dataset's license permits your intended use (research, redistribution
  of derived results, etc.) before including any results in a publication.
- Do not commit dataset files, even small ones — use download scripts so the repo
  stays lightweight and reproducible from source.
