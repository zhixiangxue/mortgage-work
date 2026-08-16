// Single source of truth for installer downloads.
//
// OSS keeps EVERY released zip — new versions are added on top, old ones
// are never deleted. The list below is ordered newest-first: the button
// probes each entry with a HEAD request and downloads the first one that
// answers OK, so a half-uploaded / removed release silently falls back
// to the previous version instead of handing the user a 404.

export const WINDOWS_VERSIONS = [
  // 'https://wcbpub.oss-cn-hangzhou.aliyuncs.com/xue/goai/MortgageWork-1.1.zip',
  'https://wcbpub.oss-cn-hangzhou.aliyuncs.com/xue/goai/MortgageWork.zip',
]

// Static default: newest known release. Used as the href before any
// probing happens, so the button works even with JS disabled.
export const DOWNLOAD_URL = WINDOWS_VERSIONS[0]

// Probe versions newest-first; resolve to the first one that answers OK.
// A clear 4xx/5xx moves on to the next (older) version; an opaque network
// failure (CORS / offline) keeps the newest as best effort.
export async function resolveDownloadUrl() {
  for (const url of WINDOWS_VERSIONS) {
    try {
      const res = await fetch(url, { method: 'HEAD', cache: 'no-store' })
      if (res.ok) return url
      if (res.status >= 400 && res.status < 600) continue
    } catch {
      return url
    }
  }
  return DOWNLOAD_URL
}
