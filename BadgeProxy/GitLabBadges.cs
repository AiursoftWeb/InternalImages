using System.Globalization;
using System.Net;
using System.Text.Json;

namespace BadgeProxy;

public sealed record Snapshot(string Status, double? Coverage, DateTimeOffset Expires, string? DefaultBranch = null, bool Found = true);

public sealed class GitLabBadges(HttpClient client, ILogger logger)
{
    private readonly Dictionary<string, Task<Snapshot>> entries = new(StringComparer.OrdinalIgnoreCase);
    private readonly object cacheLock = new();
    private readonly SemaphoreSlim upstreamSlots = new(4, 4);
    private DateTimeOffset windowStart = DateTimeOffset.UtcNow;
    private int refreshes;

    public Task<Snapshot> GetAsync(string project, CancellationToken cancellationToken)
    {
        Task<Snapshot> task;
        lock (cacheLock)
        {
            var now = DateTimeOffset.UtcNow;
            if (entries.TryGetValue(project, out var existing) &&
                (!existing.IsCompleted || existing.IsCompletedSuccessfully && existing.Result.Expires > now))
                return existing.WaitAsync(cancellationToken);
            // Bound memory and anonymous refresh traffic without maintaining a project list.
            foreach (var expired in entries.Where(e => e.Value.IsCompleted && (!e.Value.IsCompletedSuccessfully || e.Value.Result.Expires <= now)).Select(e => e.Key).ToArray())
                entries.Remove(expired);
            if (now - windowStart >= TimeSpan.FromMinutes(1))
            {
                windowStart = now;
                refreshes = 0;
            }
            if (entries.Count >= 256 || refreshes >= 120)
                return Task.FromResult(new Snapshot("unknown", null, now));
            refreshes++;
            task = RefreshAsync(project);
            entries[project] = task;
        }
        return task.WaitAsync(cancellationToken);
    }

    private async Task<Snapshot> RefreshAsync(string project)
    {
        // Do not hold the cache lock during upstream IO or tie shared refreshes to one reader.
        await Task.Yield();
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        var status = "unknown";
        double? coverage = null;
        string? branch = null;
        var found = true;
        try
        {
            await upstreamSlots.WaitAsync(deadline.Token);
            try
            {
                var projectPath = $"projects/{Uri.EscapeDataString("aiursoft/" + project)}";
                using var metadata = await ReadAsync(projectPath, deadline.Token);
                if (!string.Equals(metadata.RootElement.GetProperty("path_with_namespace").GetString(), "aiursoft/" + project, StringComparison.OrdinalIgnoreCase))
                    throw new JsonException("Unexpected project path.");
                branch = metadata.RootElement.GetProperty("default_branch").GetString();
                if (!string.IsNullOrEmpty(branch))
                {
                    var path = projectPath + "/pipelines";
                    using var list = await ReadAsync($"{path}?ref={Uri.EscapeDataString(branch)}&order_by=id&sort=desc&per_page=1", deadline.Token);
                    if (list.RootElement.GetArrayLength() > 0)
                    {
                        var id = list.RootElement[0].GetProperty("id").GetInt64();
                        using var detail = await ReadAsync($"{path}/{id}", deadline.Token);
                        var root = detail.RootElement;
                        if (root.GetProperty("ref").GetString() != branch)
                            throw new JsonException("Unexpected pipeline ref.");
                        var state = root.GetProperty("status").GetString();
                        status = state switch
                        {
                            "success" => "passed",
                            "failed" or "running" or "pending" or "canceled" or "skipped" or "manual" or "scheduled" or "created" or "preparing" or "waiting_for_resource" => state,
                            _ => "unknown"
                        };
                        if (root.TryGetProperty("coverage", out var raw) && raw.ValueKind is JsonValueKind.String or JsonValueKind.Number &&
                            double.TryParse(raw.ValueKind == JsonValueKind.String ? raw.GetString() : raw.GetRawText(), NumberStyles.Float, CultureInfo.InvariantCulture, out var number) &&
                            double.IsFinite(number) && number is >= 0 and <= 100)
                            coverage = number;
                    }
                }
            }
            finally { upstreamSlots.Release(); }
        }
        catch (HttpRequestException error) when (error.StatusCode == HttpStatusCode.NotFound && branch is null)
        {
            status = "unknown";
            coverage = null;
            found = false;
        }
        catch (Exception error) when (error is HttpRequestException or OperationCanceledException or JsonException or InvalidOperationException or FormatException or KeyNotFoundException)
        {
            status = "unknown";
            coverage = null;
            // Never log upstream response bodies, headers, URLs or credential-bearing exceptions.
            logger.LogWarning("GitLab badge lookup failed for {Project} ({ErrorType}).", project, error.GetType().Name);
        }
        return new Snapshot(status, coverage, DateTimeOffset.UtcNow.AddMinutes(status == "unknown" || coverage is null ? 1 : 30), branch, found);
    }

    private async Task<JsonDocument> ReadAsync(string path, CancellationToken cancellationToken)
    {
        using var response = await client.GetAsync(path, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
        response.EnsureSuccessStatusCode();
        // API responses contain one project/pipeline only; bound transfer size and JSON depth.
        using var buffer = new MemoryStream();
        await using var body = await response.Content.ReadAsStreamAsync(cancellationToken);
        var block = new byte[8192];
        int size;
        while ((size = await body.ReadAsync(block, cancellationToken)) > 0)
        {
            if (buffer.Length + size > 131072) throw new JsonException("Pipeline response too large.");
            buffer.Write(block, 0, size);
        }
        return JsonDocument.Parse(buffer.ToArray(), new JsonDocumentOptions { MaxDepth = 16 });
    }
}
