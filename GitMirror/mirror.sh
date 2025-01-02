#!/bin/bash

########################################
# Colorful log functions
########################################
info() {
  # Print green text
  echo -e "\033[0;32m[INFO] $*\033[0m"
}

warn() {
  # Print yellow text
  echo -e "\033[0;33m[WARN] $*\033[0m"
}

error() {
  # Print red text
  echo -e "\033[0;31m[ERROR] $*\033[0m"
}

########################################
# Clone or update a single repo
# Arguments:
#   1) JSON string representing the repo (includes .name, .http_url_to_repo, etc)
#   2) Local path to clone/update
########################################
clone_or_update_repo() {
  local repo_json=$1
  local destination_path=$2

  local repo_name
  local repo_url
  repo_name=$(echo "$repo_json" | jq -r .name)
  repo_url=$(echo "$repo_json" | jq -r .http_url_to_repo)

  local repo_path="${destination_path}/${repo_name}"

  if [ ! -d "$repo_path" ]; then
    info "Cloning '${repo_name}' into '${repo_path}' ..."
    git clone "$repo_url" "$repo_path"
    
    cd "$repo_path" || exit 1
    # Fetch all branches
    git fetch --all
    # Track all remote branches
    track_remote_branches "$repo_name"
    # Pull all
    git pull --all
    
    cd - &>/dev/null || exit 1
    info "Cloned '${repo_name}' successfully."
  else
    info "Updating '${repo_name}' in '${repo_path}' ..."
    cd "$repo_path" || exit 1
    
    # Clean untracked files
    git clean -fdx
    # Fetch all and prune deleted branches
    git fetch --all --prune
    
    # Track all remote branches
    track_remote_branches "$repo_name"
    # Pull all
    git pull --all
    
    # Ensure we switch to the default branch
    local default_branch
    default_branch=$(git symbolic-ref refs/remotes/origin/HEAD | sed 's@^refs/remotes/origin/@@')
    git checkout "$default_branch" 2>/dev/null || git checkout -b "$default_branch"
    git reset --hard "origin/$default_branch"
    
    cd - &>/dev/null || exit 1
    info "Fetched all branches for '${repo_name}' successfully."
  fi

  # Add or update github remote
  add_github_remote "$repo_name" "$repo_path" "$repo_url"
  # Push to GitHub
  push_to_github "$repo_name" "$repo_path"
}

########################################
# Track all remote branches to local
# Arguments:
#   1) Repo name (for logging)
########################################
track_remote_branches() {
  local repo_name=$1

  # We only want to track remote branches that don't exist locally yet
  local remote_branches
  remote_branches=$(git branch -r | grep -v '\->')

  for rb in $remote_branches; do
    local local_branch_name="${rb##origin/}"

    # If the local branch does not exist, track it
    if ! git rev-parse --verify "$local_branch_name" &>/dev/null; then
      info "Tracking remote branch '${rb}' locally as '${local_branch_name}' in '${repo_name}' ..."
      git branch --track "${local_branch_name}" "${rb}" 2>/dev/null || true
    else
      info "Local branch '${local_branch_name}' in '${repo_name}' already exists, skipping."
    fi
  done
}

########################################
# Add GitHub remote based on repo URL
# Arguments:
#   1) Repo name
#   2) Local repo path
#   3) Original repo URL (used to decide which GitHub account to push to)
########################################
add_github_remote() {
  local repo_name=$1
  local repo_path=$2
  local repo_url=$3

  cd "$repo_path" || return

  info "Configuring GitHub remote for '${repo_name}' ..."

  # Decide which GitHub org or user to use
  local github_base_url="https://github.com"
  local github_url=""
  if [[ "$repo_url" == *"/aiursoft/"* ]]; then
    # Mirror to aiursoftweb
    github_url="${github_base_url}/aiursoftweb/${repo_name}.git"
  elif [[ "$repo_url" == *"/anduin/"* ]]; then
    # Mirror to anduin2017
    github_url="${github_base_url}/anduin2017/${repo_name}.git"
  else
    warn "Unknown repository path: '${repo_url}'. Skipping remote config."
    cd - &>/dev/null || return
    return
  fi

  # Build the remote url with token
  local github_remote_url="https://anduin2017:${GITHUB_PAT}@${github_url#https://}"

  # If remote 'github' exists, update it; otherwise add it
  if git remote | grep -q "github"; then
    git remote set-url github "$github_remote_url"
    info "Updated existing GitHub remote for '${repo_name}'."
  else
    git remote add github "$github_remote_url"
    info "Added new GitHub remote for '${repo_name}'."
  fi

  cd - &>/dev/null || return
}

########################################
# Push local repo to GitHub
# Arguments:
#   1) Repo name
#   2) Local path
########################################
push_to_github() {
  local repo_name=$1
  local repo_path=$2

  cd "$repo_path" || return
  info "Pushing '${repo_name}' to GitHub ..."
  
  # Push all branches
  git push github --all --force
  # Push all tags
  git push github --tags --force
  
  cd - &>/dev/null || return
  info "Pushed '${repo_name}' to GitHub."
}

########################################
# Clone or update multiple repositories
# Arguments:
#   1) Array name (indirect)
#   2) Local path to clone/update
########################################
clone_or_update_repositories() {
  local repos=("${!1}")
  local destination_path=$2

  for repo in "${repos[@]}"; do
    clone_or_update_repo "$repo" "$destination_path"
  done
}

########################################
# Main entry: fetch group/user repos from GitLab 
# and mirror them to GitHub
########################################
reset_git_repos() {
  info "Starting to clone or update all repositories..."

  local gitlab_base_url="https://gitlab.aiursoft.cn"
  local api_url="${gitlab_base_url}/api/v4"
  local group_name="Aiursoft"
  local user_name="Anduin"

  local destination_path_aiursoft="/opt/Source/Repos/Aiursoft"
  local destination_path_anduin="/opt/Source/Repos/Anduin"

  mkdir -p "$destination_path_aiursoft"
  mkdir -p "$destination_path_anduin"

  # Get group ID
  local group_url="${api_url}/groups?search=${group_name}"
  local group_request
  group_request=$(curl -s "$group_url")
  local group_id
  group_id=$(echo "$group_request" | jq -r '.[0].id')

  if [ -z "$group_id" ] || [ "$group_id" == "null" ]; then
    error "Failed to fetch group ID for '${group_name}'. Exiting."
    exit 1
  fi

  # Get user ID
  local user_url="${api_url}/users?username=${user_name}"
  local user_request
  user_request=$(curl -s "$user_url")
  local user_id
  user_id=$(echo "$user_request" | jq -r '.[0].id')

  if [ -z "$user_id" ] || [ "$user_id" == "null" ]; then
    error "Failed to fetch user ID for '${user_name}'. Exiting."
    exit 1
  fi

  # Fetch all public projects under Aiursoft group
  local repo_url_aiursoft="${api_url}/groups/${group_id}/projects?simple=true&per_page=999&visibility=public&page=1"
  local repos_aiursoft
  repos_aiursoft=$(curl -s "$repo_url_aiursoft" | jq -c '.[]')
  if [ -z "$repos_aiursoft" ]; then
    error "Failed to fetch any repositories for group '${group_name}'. Exiting."
    exit 1
  fi

  # Fetch all public projects under Anduin user
  local repo_url_anduin="${api_url}/users/${user_id}/projects?simple=true&per_page=999&visibility=public&page=1"
  local repos_anduin
  repos_anduin=$(curl -s "$repo_url_anduin" | jq -c '.[]')
  if [ -z "$repos_anduin" ]; then
    error "Failed to fetch any repositories for user '${user_name}'. Exiting."
    exit 1
  fi

  # Convert repos to arrays
  local repos_aiursoft_array=()
  while IFS= read -r line; do
    repos_aiursoft_array+=("$line")
  done <<< "$repos_aiursoft"

  local repos_anduin_array=()
  while IFS= read -r line; do
    repos_anduin_array+=("$line")
  done <<< "$repos_anduin"

  # Clone or update group repos
  clone_or_update_repositories repos_aiursoft_array[@] "$destination_path_aiursoft"
  # Clone or update user repos
  clone_or_update_repositories repos_anduin_array[@] "$destination_path_anduin"
}

########################################
# Script starts here
########################################
info "Reading token from /run/secrets/github-token ..."
token=$(cat /run/secrets/github-token 2>/dev/null)

if [ -z "$token" ]; then
  error "No GitHub token found. Exiting."
  exit 1
fi

export GITHUB_PAT=$token

reset_git_repos
info "All operations completed."
