#!/bin/bash

clone_or_update_repo() {
    local repo=$1
    local destination_path=$2
    local repo_name=$(echo "$repo" | jq -r .name)
    local repo_url=$(echo "$repo" | jq -r .http_url_to_repo)
    local repo_path="${destination_path}/${repo_name}"

    if [ ! -d "$repo_path" ]; then
        echo -e "\033[0;32mCloning $repo_name to $repo_path...\033[0m"
        git clone "$repo_url" "$repo_path"
        echo -e "\033[0;32mCloned $repo_name to $repo_path\033[0m"
    else
        echo -e "\033[0;32mUpdating $repo_name at $repo_path...\033[0m"
        cd "$repo_path"
        mainBranch=$(git remote show origin | grep 'HEAD branch' | cut -d' ' -f5)
        git clean -fdx
        git reset --hard HEAD
        git fetch
        git reset --hard "origin/$mainBranch"
        echo -e "\033[0;32mUpdated $repo_name at $repo_path on branch $mainBranch\033[0m"
        cd - > /dev/null
    fi
}

clone_or_update_repositories() {
    local repos=("${!1}")
    local destination_path=$2

    for repo in "${repos[@]}"; do
        clone_or_update_repo "$repo" "$destination_path"
    done
}

reset_git_repos() {
    echo -e "\033[0;32mCloning or updating all repos...\033[0m"

    local gitlab_base_url="https://gitlab.aiursoft.cn"
    local api_url="${gitlab_base_url}/api/v4"
    local group_name="Aiursoft"
    local user_name="Anduin"

    local destination_path_aiursoft="$HOME/Source/Repos/Aiursoft"
    local destination_path_anduin="$HOME/Source/Repos/Anduin"

    mkdir -p "$destination_path_aiursoft"
    mkdir -p "$destination_path_anduin"

    local group_url="${api_url}/groups?search=${group_name}"
    local group_request=$(curl -s "$group_url")
    local group_id=$(echo "$group_request" | jq -r '.[0].id')

    if [ -z "$group_id" ]; then
        echo "Error: Unable to fetch group ID for $group_name"
        exit 1
    fi

    local user_url="${api_url}/users?username=${user_name}"
    local user_request=$(curl -s "$user_url")
    local user_id=$(echo "$user_request" | jq -r '.[0].id')

    if [ -z "$user_id" ]; then
        echo "Error: Unable to fetch user ID for $user_name"
        exit 1
    fi

    local repo_url_aiursoft="${api_url}/groups/${group_id}/projects?simple=true&per_page=999&visibility=public&page=1"
    local repo_url_anduin="${api_url}/users/${user_id}/projects?simple=true&per_page=999&visibility=public&page=1"

    local repos_aiursoft=$(curl -s "$repo_url_aiursoft" | jq -c '.[]')
    local repos_anduin=$(curl -s "$repo_url_anduin" | jq -c '.[]')

    if [ -z "$repos_aiursoft" ]; then
        echo "Error: Unable to fetch repositories for group $group_name"
        exit 1
    fi

    if [ -z "$repos_anduin" ]; then
        echo "Error: Unable to fetch repositories for user $user_name"
        exit 1
    fi

    repos_aiursoft_array=()
    while IFS= read -r line; do
        repos_aiursoft_array+=("$line")
    done <<< "$repos_aiursoft"

    repos_anduin_array=()
    while IFS= read -r line; do
        repos_anduin_array+=("$line")
    done <<< "$repos_anduin"

    clone_or_update_repositories repos_aiursoft_array[@] "$destination_path_aiursoft"
    clone_or_update_repositories repos_anduin_array[@] "$destination_path_anduin"
}

reset_git_repos
