    # 解析出需要的信息
#!/bin/bash

clone_or_update_repo() {
    local repo=$1
    local destination_path=$2

    # 解析出需要的信息
    local repo_name=$(echo "$repo" | jq -r .name)
    local repo_url=$(echo "$repo" | jq -r .http_url_to_repo)
    local repo_path="${destination_path}/${repo_name}"

    # 如果不存在该目录，先 clone
    if [ ! -d "$repo_path" ]; then
        echo -e "\033[0;32mCloning $repo_name to $repo_path...\033[0m"
        git clone "$repo_url" "$repo_path"
        echo -e "\033[0;32mCloned $repo_name to $repo_path\033[0m"
    else
        echo -e "\033[0;32mUpdating $repo_name at $repo_path...\033[0m"
        cd "$repo_path"

        # 清理并获取所有远程分支
        git clean -fdx
        # 同时拉取所有分支、所有标签，并删除本地已在远程删掉的分支
        git fetch --all --prune

        # 可以让本地的 HEAD 指向默认分支（从 origin/HEAD 获取）
        # 这样本地默认签出的分支会与远程保持一致
        defaultBranch=$(git symbolic-ref refs/remotes/origin/HEAD | sed 's@^refs/remotes/origin/@@')
        git checkout "$defaultBranch" || git checkout -b "$defaultBranch"
        git reset --hard "origin/$defaultBranch"

        echo -e "\033[0;32mFetched all branches for $repo_name at $repo_path\033[0m"
        cd - > /dev/null
    fi

    # 添加（或更新）GitHub 的 remote，并 push
    add_github_remote "$repo_name" "$repo_path" "$repo_url"
    push_to_github "$repo_name" "$repo_path"
}

add_github_remote() {
    echo -e "\033[0;32mAdding github remote for $1...\033[0m"
    local repo_name=$1
    local repo_path=$2
    local repo_url=$3  # 新增参数，用来判断要推送到哪个 GitHub 帐号下

    cd "$repo_path"

    # 设置 base url
    github_base_url="https://github.com"
    # 按照路径判断要用哪个 GitHub 帐号
    if [[ "$repo_url" == *"/aiursoft/"* ]]; then
        github_url="${github_base_url}/aiursoftweb/${repo_name}.git"
    elif [[ "$repo_url" == *"/anduin/"* ]]; then
        github_url="${github_base_url}/anduin2017/${repo_name}.git"
    else
        echo "Unknown repository path: $repo_path"
        cd - > /dev/null
        return
    fi

    # 配置 github remote，需要带上鉴权信息
    github_remote_url="https://anduin2017:${GITHUB_PAT}@${github_url#https://}"

    if git remote | grep -q "github"; then
        git remote set-url github "$github_remote_url"
        echo -e "\033[0;32mUpdated github remote for $repo_name\033[0m"
    else
        git remote add github "$github_remote_url"
        echo -e "\033[0;32mAdded github remote for $repo_name\033[0m"
    fi

    cd - > /dev/null
}

push_to_github() {
    echo -e "\033[0;32mPushing $1 to github...\033[0m"
    local repo_name=$1
    local repo_path=$2

    cd "$repo_path"
    # 推送所有本地分支、所有标签到 GitHub
    git push github --all --force
    git push github --tags --force
    echo -e "\033[0;32mPushed $repo_name to github\033[0m"
    cd - > /dev/null
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

    local destination_path_aiursoft="/opt/Source/Repos/Aiursoft"
    local destination_path_anduin="/opt/Source/Repos/Anduin"

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

    # 获取 Aiursoft group 下的所有公开项目
    local repo_url_aiursoft="${api_url}/groups/${group_id}/projects?simple=true&per_page=999&visibility=public&page=1"
    # 获取 Anduin 用户下的所有公开项目
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

    # 转成数组
    repos_aiursoft_array=()
    while IFS= read -r line; do
        repos_aiursoft_array+=("$line")
    done <<< "$repos_aiursoft"

    repos_anduin_array=()
    while IFS= read -r line; do
        repos_anduin_array+=("$line")
    done <<< "$repos_anduin"

    # 克隆或者更新
    clone_or_update_repositories repos_aiursoft_array[@] "$destination_path_aiursoft"
    clone_or_update_repositories repos_anduin_array[@] "$destination_path_anduin"
}

echo "Reading token from /run/secrets/github-token"
token=$(cat /run/secrets/github-token)

# 如果 token 为空，则退出
if [ -z "$token" ]; then
    echo "No token provided."
    exit 1
fi

GITHUB_PAT=$token

reset_git_repos
