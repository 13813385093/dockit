#!/usr/bin/env bash
#
# 每日从 Gitee master 拉取，强制同步到 GitHub main，并打日期标签
#
# 只有内容真的变化时才推 main、才打标签；同一天多次运行只产生一个标签。
#
set -euo pipefail

GITEE_URL="${GITEE_URL:-https://gitee.com/learnhow/dockit.git}"
GITHUB_URL="${GITHUB_URL:-origin}"

log() { printf '[sync] %s\n' "$*"; }
mask() { sed -E 's#//[^@/]*@#//***@#g'; }

git config user.name  'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'

git remote add gitee "$GITEE_URL" 2>/dev/null || git remote set-url gitee "$GITEE_URL"
git fetch --quiet --tags gitee master

NEW="$(git rev-parse FETCH_HEAD)"
log "Gitee master = $NEW"

CUR=""
if out="$(git ls-remote "$GITHUB_URL" refs/heads/main 2>&1)"; then
  CUR="$(printf '%s\n' "$out" | awk '{print $1}' | head -1)"
else
  printf '%s\n' "$out" | mask; log "无法读取 GitHub main"; exit 1
fi

if [ -n "$CUR" ] && [ "$CUR" = "$NEW" ]; then
  log "内容无变化，跳过"
  exit 0
fi

TODAY="$(date -u +%Y.%m.%d)"
PREFIX="v${TODAY}."
max=0
if out="$(git ls-remote --tags "$GITHUB_URL" "refs/tags/${PREFIX}*" 2>&1)"; then
  while IFS=$'\t' read -r _sha ref; do
    [ -n "${ref:-}" ] || continue
    name="${ref#refs/tags/}"; name="${name%\^\{\}}"
    n="${name#"$PREFIX"}"
    case "$n" in ''|*[!0-9]*) continue ;; esac
    [ "$n" -gt "$max" ] && max="$n"
  done <<< "$out"
else
  printf '%s\n' "$out" | mask; log "读取标签失败"; exit 1
fi

TAG="${PREFIX}$((max + 1))"
log "打标签 $TAG"

git tag -a "$TAG" "$NEW" -m "sync ${NEW:0:8} from gitee master"

log "推送 -> GitHub main（强制覆盖）"
if ! out="$(git push --force --quiet "$GITHUB_URL" "$NEW:refs/heads/main" 2>&1)"; then
  printf '%s\n' "$out" | mask; log "推送 main 失败"; exit 1
fi
printf '%s\n' "$out" | mask

log "推送标签 $TAG"
if ! out="$(git push --quiet "$GITHUB_URL" "refs/tags/$TAG" 2>&1)"; then
  printf '%s\n' "$out" | mask; log "推送标签失败"; exit 1
fi
printf '%s\n' "$out" | mask

log "完成: main <- ${NEW:0:8}, tag $TAG"
