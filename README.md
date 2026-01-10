# Latex-Sync

Notion/Markdown <=> Latex sync with GitHub Actions and Overleaf

## Overleaf push
- push to overleaf is much faster through actions than local push
- See https://github.com/denkiwakame/overleaf-mirroring for example
- `git push` in `overleaf` branch
- `gh workflow run overleaf.yaml -f overleaf_project_id="xxxxxxxxxxxx"` in remote (`main` branch)
- pull from overleaf to `overleaf` branch to identify any overleaf changes

## Notion sync
- `make notion` in local
- `gh workflow run notion.yaml -f path="path-to-notion-download"` in remote (`notion` branch)

## Overleaf initialization (only once)
- `git checkout -b overleaf`
- `git remote add overleaf https://git.overleaf.com/xxxxxxxxxxxx`
- `git fetch overleaf` might be needed
- `git merge overleaf/master --allow-unrelated-histories`
- `git push overleaf HEAD:master`
