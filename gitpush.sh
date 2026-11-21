#!/usr/bin/env bash
set -e

REPO=~/Dotfile-save
CFG=~/.config

# клонируем, если ещё нет
[ -d "$REPO/.git" ] || git clone https://github.com/HRZ272/Dotfile-save.git "$REPO"
cd "$REPO"
git pull --rebase

# 1. всё, что уже лежит в репе и есть в ~/.config, синкаем (с удалением старого)
for item in */ ; do
  name="${item%/}"
  case "$name" in hypr_backup|bin|kicad|libreoffice|menus|.git) continue;; esac
  [ -d "$CFG/$name" ] && rsync -a --delete \
    --exclude='__pycache__' --exclude='*.log' --exclude='cache' \
    "$CFG/$name/" "$REPO/$name/"
done

# 2. одиночные файлы из корня репы
for f in *; do
  [ -f "$f" ] && [ -f "$CFG/$f" ] && cp -a "$CFG/$f" "$REPO/$f"
done

# 3. вложенные пути
rsync -a --delete "$CFG/kicad/10.0/"                 kicad/10.0/
rsync -a --delete "$CFG/libreoffice/4/user/"         libreoffice/4/user/
rsync -a --delete "$CFG/menus/applications-merged/"  menus/applications-merged/

# 4. новые папки, которых ещё нет в репе — добавляй сюда вручную:
# for d in newapp; do rsync -a "$CFG/$d/" "$REPO/$d/"; done

git add -A
git status --short
