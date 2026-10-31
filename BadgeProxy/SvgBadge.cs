using System.Security;

namespace BadgeProxy;

public static class SvgBadge
{
    public static string Render(string label, string value)
    {
        var left = label.Length * 7 + 12;
        var right = value.Length * 7 + 12;
        var width = left + right;
        var color = value switch
        {
            "passed" => "#4c1",
            "failed" => "#e05d44",
            "running" => "#007ec6",
            "pending" or "manual" or "scheduled" or "waiting_for_resource" => "#dfb317",
            "unknown" or "canceled" or "skipped" or "created" or "preparing" => "#9f9f9f",
            _ => "#007ec6"
        };
        label = SecurityElement.Escape(label)!;
        value = SecurityElement.Escape(value)!;
        return $"""
            <svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="20" role="img" aria-label="{label}: {value}">
              <title>{label}: {value}</title>
              <clipPath id="clip"><rect width="{width}" height="20" rx="3"/></clipPath>
              <g clip-path="url(#clip)"><path fill="#555" d="M0 0h{left}v20H0z"/><path fill="{color}" d="M{left} 0h{right}v20H{left}z"/></g>
              <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">
                <text x="{left / 2}" y="14">{label}</text><text x="{left + right / 2}" y="14">{value}</text>
              </g>
            </svg>
            """;
    }
}
