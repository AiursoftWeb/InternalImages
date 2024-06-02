#!/bin/bash

clone_git_repositories() {
    local repos=("$@")
    local destination_path=$2

    for repo in "${repos[@]}"; do
        local repo_name=$(echo "$repo" | jq -r .name)
        local repo_url=$(echo "$repo" | jq -r .http_url_to_repo)
        local repo_path="${destination_path}/${repo_name}"

        if [ ! -d "$repo_path" ]; then
            git clone "$repo_url" "$repo_path"
            echo "Cloned $repo_name to $repo_path"
        else
            echo "$repo_name already exists at $repo_path, skipping."
        fi
    done
}

reset_git_repos() {
    echo "Deleting items..."
    rm -rf "$HOME/Source/Repos/Aiursoft"
    rm -rf "$HOME/Source/Repos/Anduin"
    echo "Items deleted!"

    sleep 1

    echo -e "\033[0;32mCloning all repos...\033[0m"

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

    IFS=$'\n' read -rd '' -a repos_aiursoft_array <<<"$repos_aiursoft"
    IFS=$'\n' read -rd '' -a repos_anduin_array <<<"$repos_anduin"

    clone_git_repositories "${repos_aiursoft_array[@]}" "$destination_path_aiursoft"
    clone_git_repositories "${repos_anduin_array[@]}" "$destination_path_anduin"

    pin_repos
}

# This function should be defined to perform whatever pinning is needed.
pin_repos() {
    echo "Pinning repositories... (Implement this function as needed)"
}

reset_git_repos
