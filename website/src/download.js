// Single source of truth for installer downloads.
//
// OSS keeps EVERY released zip — new versions are added on top, old ones
// are never deleted. Each platform list is ordered newest-first: picking a
// platform probes its entries with a HEAD request and downloads the first
// that answers OK, so a half-uploaded / removed release silently falls back
// to the previous version instead of handing the user a 404.
//
// Naming convention: {Product}-{version}-{platform}-{arch}.zip
// (e.g. MortgageWork-0.1.0-macos-x64.zip). The arch suffix matters on
// macOS — x64 (Intel) and arm64 (M-chip) are different builds.

export const VERSIONS = {
  windows: [
    'https://wcbpub.oss-cn-hangzhou.aliyuncs.com/xue/goai/MortgageWork-0.1.0-windows-x64.zip',
    // Legacy pre-convention release — kept as fallback while it stays on OSS.
    'https://wcbpub.oss-cn-hangzhou.aliyuncs.com/xue/goai/MortgageWork.zip',
  ],
  macos: [
    // Intel build. Running it on M-chip Macs is UNTESTED (the bundle ships
    // native libs that may use instructions the translation layer can't
    // handle). A native MortgageWork-x.x.x-macos-arm64.zip entry slots in
    // on top when it ships.
    'https://wcbpub.oss-cn-hangzhou.aliyuncs.com/xue/goai/MortgageWork-0.1.0-macos-x64.zip',
  ],
}

// Dropdown entries — visitors pick their own platform. No UA sniffing:
// browsers misreport (iPadOS poses as Mac, Windows ARM reports oddly) and
// people always know their own machine best.
export const PLATFORMS = [
  { id: 'windows', icon: 'windows', label: 'Windows', detail: 'x64 · Win 10+' },
  { id: 'macos', icon: 'apple', label: 'macOS', detail: 'Intel · 12+' },
]

// Static default: newest known Windows release. Used as the button href so
// it still downloads something sensible with JS disabled.
export const DOWNLOAD_URL = VERSIONS.windows[0]

// Probe one platform's versions newest-first; resolve to the first that
// answers OK. A clear 4xx/5xx moves on to the next (older) version; an
// opaque network failure (CORS / offline) keeps the newest as best effort.
export async function resolveDownloadUrl(platform) {
  const list = VERSIONS[platform] || []
  for (const url of list) {
    try {
      const res = await fetch(url, { method: 'HEAD', cache: 'no-store' })
      if (res.ok) return url
      if (res.status >= 400 && res.status < 600) continue
    } catch {
      return url
    }
  }
  return list[0] || DOWNLOAD_URL
}

// HEAD probes are fired once on page load (preloadDownloadUrls) and their
// promises cached, so a click hands the URL straight to the browser with
// zero network wait — the probe round-trip never sits between the click
// and the download again.
const probed = {}

export function preloadDownloadUrls() {
  for (const p of PLATFORMS) getDownloadUrl(p.id)
}

// Returns the cached probe promise for a platform, starting one if needed
// (e.g. when called before preloadDownloadUrls ran).
export function getDownloadUrl(platform) {
  if (!probed[platform]) probed[platform] = resolveDownloadUrl(platform)
  return probed[platform]
}
