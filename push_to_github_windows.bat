@echo off
REM Publish CAN to GitHub (Windows)

set REPO_NAME=can-framework
set VISIBILITY=public

git init
git checkout -b main

git add .
git commit -m "Initial release: CAN framework + backend"

gh auth login

gh repo create %REPO_NAME% --%VISIBILITY% --source=. --remote=origin --push

echo Repo: https://github.com/value-coordination-CAN/can-framework
echo Docs: https://value-coordination-CAN.github.io/can-framework/
