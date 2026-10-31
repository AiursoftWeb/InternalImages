using System.Globalization;
using System.Text.Json;

namespace BadgeProxy;

public sealed record Snapshot(string Status, double? Coverage, DateTimeOffset Expires);

public sealed class GitLabBadges(HttpClient client, IEnumerable<string> projects, ILogger logger)
{
    private sealed class Entry
    {
        public readonly SemaphoreSlim Gate = new(1, 1);
        public Snapshot? Snapshot;
    }

    private readonly Dictionary<string, Entry> entries = projects.ToDictionary(p => p, _ => new Entry(), StringComparer.OrdinalIgnoreCase);
    private readonly SemaphoreSlim upstreamSlots = new(4, 4);

    public async Task<Snapshot> GetAsync(string project, string branch, CancellationToken cancellationToken)
    {
        var entry = entries[project];
        await entry.Gate.WaitAsync(cancellationToken);
        try
        {
            if (entry.Snapshot is { } current && current.Expires > DateTimeOffset.UtcNow) return current;
            // A disconnected reader must not cancel the refresh shared by other readers.
            using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(5));
            var status = "unknown";
            double? coverage = null;
            try
            {
                await upstreamSlots.WaitAsync(deadline.Token);
                try
                {
                    var path = $"projects/{Uri.EscapeDataString("aiursoft/" + project)}/pipelines";
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
                finally { upstreamSlots.Release(); }
            }
            catch (Exception error) when (error is HttpRequestException or OperationCanceledException or JsonException or InvalidOperationException or FormatException or KeyNotFoundException)
            {
                status = "unknown";
                coverage = null;
                // Never log upstream response bodies, headers, URLs or credential-bearing exceptions.
                logger.LogWarning("GitLab badge lookup failed for {Project} ({ErrorType}).", project, error.GetType().Name);
            }
            return entry.Snapshot = new Snapshot(status, coverage, DateTimeOffset.UtcNow.AddMinutes(1));
        }
        finally { entry.Gate.Release(); }
    }

    private async Task<JsonDocument> ReadAsync(string path, CancellationToken cancellationToken)
    {
        using var response = await client.GetAsync(path, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
        response.EnsureSuccessStatusCode();
        // API responses contain one pipeline only; bound both transfer size and JSON depth.
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
