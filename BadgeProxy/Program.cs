using System.Globalization;
using BadgeProxy;

if (args.Contains("--healthcheck"))
{
    using var probe = new HttpClient { Timeout = TimeSpan.FromSeconds(3) };
    try
    {
        using var response = await probe.GetAsync("http://127.0.0.1:5000/health");
        return response.IsSuccessStatusCode ? 0 : 1;
    }
    catch (HttpRequestException) { return 1; }
    catch (TaskCanceledException) { return 1; }
}

var builder = WebApplication.CreateBuilder(args);
builder.Logging.AddFilter("Microsoft.AspNetCore", LogLevel.Warning);
var upstream = builder.Configuration["GITLAB_URL"] ?? "http://gitlab_gitlab";
if (!Uri.TryCreate(upstream.TrimEnd('/') + "/api/v4/", UriKind.Absolute, out var api) ||
    api.Scheme is not ("http" or "https") || !string.IsNullOrEmpty(api.UserInfo) ||
    !string.IsNullOrEmpty(api.Query) || !string.IsNullOrEmpty(api.Fragment) || api.AbsolutePath != "/api/v4/")
    throw new InvalidOperationException("GITLAB_URL must be an HTTP(S) origin.");
var token = builder.Configuration["GITLAB_ACCESS_TOKEN"];
if (string.IsNullOrWhiteSpace(token))
    throw new InvalidOperationException("GITLAB_ACCESS_TOKEN is required.");
var projects = (builder.Configuration["ALLOWED_PROJECTS"] ?? "").Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
    .Select(item => item.Split(':', 2)).ToArray();
if (projects.Length == 0 || projects.Any(p => p.Length != 2 ||
    !System.Text.RegularExpressions.Regex.IsMatch(p[0], "^[a-z0-9][a-z0-9_-]*$", System.Text.RegularExpressions.RegexOptions.CultureInvariant) ||
    string.IsNullOrWhiteSpace(p[1]) || p[1].Contains('/') || p[1].Contains('\\')))
    throw new InvalidOperationException("ALLOWED_PROJECTS must contain project:default-branch entries.");
var allowed = projects.ToDictionary(p => p[0], p => p[1], StringComparer.OrdinalIgnoreCase);
using var client = new HttpClient(new SocketsHttpHandler { AllowAutoRedirect = false, MaxConnectionsPerServer = 4 })
    { BaseAddress = api, Timeout = Timeout.InfiniteTimeSpan };
client.DefaultRequestHeaders.Add("PRIVATE-TOKEN", token);
client.DefaultRequestHeaders.UserAgent.ParseAdd("Aiursoft-BadgeProxy/1.0");
var app = builder.Build();
var badges = new GitLabBadges(client, allowed.Keys, app.Logger);
app.MapGet("/health", () => Results.Text("healthy"));
app.MapMethods("/aiursoft/{project}/badges/{branch}/{file}", ["GET", "HEAD"], async (HttpContext context, string project, string branch, string file) =>
{
    if (!allowed.TryGetValue(project, out var defaultBranch) || branch != defaultBranch ||
        file is not ("pipeline.svg" or "coverage.svg"))
        return Results.NotFound();
    if (context.Request.QueryString.HasValue)
        return Results.BadRequest();
    var snapshot = await badges.GetAsync(project.ToLowerInvariant(), defaultBranch, context.RequestAborted);
    var remaining = Math.Max(0, (int)(snapshot.Expires - DateTimeOffset.UtcNow).TotalSeconds);
    context.Response.Headers.CacheControl = $"public, max-age={remaining}, must-revalidate";
    context.Response.Headers["X-Content-Type-Options"] = "nosniff";
    context.Response.Headers.ContentSecurityPolicy = "default-src 'none'; sandbox";
    var coverage = file == "coverage.svg";
    var value = coverage ? snapshot.Coverage?.ToString("0.##", CultureInfo.InvariantCulture) + "%" : snapshot.Status;
    if (coverage && snapshot.Coverage is null) value = "unknown";
    return Results.Text(SvgBadge.Render(coverage ? "coverage" : "pipeline", value ?? "unknown"), "image/svg+xml; charset=utf-8");
});
await app.RunAsync();
return 0;
