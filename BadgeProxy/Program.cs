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
using var client = new HttpClient(new SocketsHttpHandler { AllowAutoRedirect = false, MaxConnectionsPerServer = 4 })
    { BaseAddress = api, Timeout = Timeout.InfiniteTimeSpan };
client.DefaultRequestHeaders.Add("PRIVATE-TOKEN", token);
client.DefaultRequestHeaders.UserAgent.ParseAdd("Aiursoft-BadgeProxy/1.0");
var app = builder.Build();
var badges = new GitLabBadges(client, app.Logger);
app.MapGet("/health", () => Results.Text("healthy"));
app.MapMethods("/aiursoft/{project}/badges/{**badgePath}", ["GET", "HEAD"], async (HttpContext context, string project, string? badgePath) =>
{
    context.Response.Headers.CacheControl = "no-store";
    if (project.Length > 128 || !System.Text.RegularExpressions.Regex.IsMatch(project, "^[a-zA-Z0-9][a-zA-Z0-9_-]*$", System.Text.RegularExpressions.RegexOptions.CultureInvariant))
        return Results.NotFound();
    var slash = badgePath?.LastIndexOf('/') ?? -1;
    if (slash < 1) return Results.NotFound();
    var branch = badgePath![..slash];
    var file = badgePath[(slash + 1)..];
    if (file is not ("pipeline.svg" or "coverage.svg")) return Results.NotFound();
    if (context.Request.QueryString.HasValue)
        return Results.BadRequest();
    var snapshot = await badges.GetAsync(project.ToLowerInvariant(), context.RequestAborted);
    if (!snapshot.Found || snapshot.DefaultBranch is not null && branch != snapshot.DefaultBranch)
        return Results.NotFound();
    context.Response.Headers["X-Content-Type-Options"] = "nosniff";
    context.Response.Headers.ContentSecurityPolicy = "default-src 'none'; sandbox";
    var coverage = file == "coverage.svg";
    var value = coverage ? snapshot.Coverage?.ToString("0.##", CultureInfo.InvariantCulture) + "%" : snapshot.Status;
    if (coverage && snapshot.Coverage is null) value = "unknown";
    return Results.Text(SvgBadge.Render(coverage ? "coverage" : "pipeline", value ?? "unknown"), "image/svg+xml; charset=utf-8");
});
await app.RunAsync();
return 0;
