#!/usr/bin/env bash
#
# master -> GitHub main 强制同步，并打日期序号标签
#
# 触发：Gitee Go 流水线，Push 事件精确匹配 master（分支合并且会产生 Push 事件）
#
# 环境变量：
#   GITHUB_TOKEN  必填。GitHub PAT，需具备目标仓库 Contents: Read and write
#   GITHUB_REPO   选填。默认 13813385093/dockit
#   GITHUB_USER   选填。默认 13813385093
#   GITHUB_URL    选填。覆盖远端地址，仅用于本地测试
#   GITEE_TOKEN   选填。提供时额外把标签推回 Gitee（Gitee 作为主库保留标签）
#   GITEE_REPO    选填。默认 learnhow/dockit
#
# 行为：
#   1. GitHub main 已与当前 master 一致 -> 不打标签、不推送，直接成功退出
#   2. 否则打标签 vYYYY.MM.DD.N（N 为当日递增序号，序号取自 GitHub 上的同名标签）
#   3. 强制推送 master -> GitHub main，再推标签
#
set -euo pipefail
export GIT_TERMINAL_PROMPT=0

log() { printf '[sync] %s\n' "$*"; }

# 遮蔽 URL 里的账号密码，避免 token 落进日志
mask() { sed -E 's#//[^@/]*@#//***@#g'; }

die() { log "错误: $*"; exit 1; }

# 推送并遮蔽输出，保留真实退出码
push() {
  local out rc
  set +e
  out="$(git push "$@" 2>&1)"
  rc=$?
  set -e
  printf '%s\n' "$out" | mask
  return $rc
}

: "${GITHUB_TOKEN:?缺少 GITHUB_TOKEN 环境变量}"
GITHUB_REPO="${GITHUB_REPO:-13813385093/dockit}"
GITHUB_USER="${GITHUB_USER:-13813385093}"
GITEE_REPO="${GITEE_REPO:-learnhow/dockit}"

if [ -n "${GITHUB_URL:-}" ]; then
  REMOTE="$GITHUB_URL"
else
  REMOTE="https://${GITHUB_USER}:${GITHUB_TOKEN}@github.com/${GITHUB_REPO}.git"
fi

git config user.name  'gitee-go[bot]'
git config user.email 'gitee-go@users.noreply.github.com'

HEAD_SHA="$(git rev-parse HEAD)"
log "master HEAD = $HEAD_SHA"

# ---- 读取 GitHub main ----
set +e
out="$(git ls-remote "$REMOTE" refs/heads/main 2>&1)"
rc=$?
set -e
[ $rc -eq 0 ] || { printf '%s\n' "$out" | mask; die "无法访问 GitHub 仓库（检查 GITHUB_TOKEN / 网络）"; }

GH_MAIN="$(printf '%s\n' "$out" | awk '{print $1}' | head -1)"

# ---- 已经是同一个提交，直接跳过（保证重复触发不产生多余标签）----
if [ -n "$GH_MAIN" ] && [ "$GH_MAIN" = "$HEAD_SHA" ]; then
  log "GitHub main 已与 master 一致，跳过同步与打标签"
  exit 0
fi

# ---- 计算标签序号 vYYYY.MM.DD.N ----
TODAY="$(date -u +%Y.%m.%d)"
PREFIX="v${TODAY}."

set +e
out="$(git ls-remote --tags "$REMOTE" "refs/tags/${PREFIX}*" 2>&1)"
rc=$?
set -e
[ $rc -eq 0 ] || { printf '%s\n' "$out" | mask; die "读取 GitHub 标签失败"; }

max=0
while IFS=$'\t' read -r _sha ref; do
  [ -n "${ref:-}" ] || continue
  name="${ref#refs/tags/}"
  name="${name%\^\{\}}"
  n="${name#"$PREFIX"}"
  case "$n" in
    ''|*[!0-9]*) continue ;;
  esac
  [ "$n" -gt "$max" ] && max="$n"
done <<< "$out"

TAG="${PREFIX}$((max + 1))"
log "本次标签 = $TAG"

git tag -a "$TAG" -m "sync ${HEAD_SHA:0:8} from Gitee master"

# ---- 推 main（强制覆盖）----
log "推送 master -> GitHub main（强制覆盖）"
push --force --quiet "$REMOTE" "HEAD:refs/heads/main" || die "推送 main 失败"

# ---- 推标签 ----
log "推送标签 $TAG -> GitHub"
push --quiet "$REMOTE" "refs/tags/${TAG}" || die "推送标签失败"

if [ -n "${GITEE_TOKEN:-}" ]; then
  log "推送标签 $TAG -> Gitee"
  push --quiet "https://oauth2:${GITEE_TOKEN}@gitee.com/${GITEE_REPO}.git" "refs/tags/${TAG}" \
    || die "推送标签到 Gitee 失败"
else
  log "未提供 GITEE_TOKEN，跳过向 Gitee 推标签"
fi

log "完成: GitHub main <- ${HEAD_SHA:0:8}, tag $TAG"
