package de.wauhundeland.fnggmapdownloader

import kotlinx.coroutines.delay
import java.net.HttpURLConnection
import java.net.URL
import java.util.logging.Logger

object VersionScanner {
    private val LOGGER: Logger = Logger.getLogger("VersionScanner")

    data class ScanResult(val version: String)

    data class TileScheme(val zoom: Int, val gridSize: Int, val extension: String)

    private enum class ProbeStatus { EXISTS, NOT_FOUND, UNKNOWN }

    private fun probeOnce(urlStr: String): ProbeStatus {
        return try {
            val connection = URL(urlStr).openConnection() as HttpURLConnection
            connection.requestMethod = "HEAD"
            connection.setRequestProperty("User-Agent", "Mozilla/5.0")
            connection.connectTimeout = 8000
            connection.readTimeout = 8000
            when (connection.responseCode) {
                200 -> ProbeStatus.EXISTS
                404 -> ProbeStatus.NOT_FOUND
                else -> ProbeStatus.UNKNOWN
            }
        } catch (e: Exception) {
            ProbeStatus.UNKNOWN
        }
    }

    // Retries on UNKNOWN (rate-limited/blocked/timeout) with generous backoff, so a temporary
    // block from hitting the CDN too fast isn't mistaken for "doesn't exist" (a clean 404 is
    // trusted immediately, no retry needed).
    private suspend fun probeUrl(urlStr: String, retries: Int = 4): Boolean {
        repeat(retries) { attempt ->
            when (probeOnce(urlStr)) {
                ProbeStatus.EXISTS -> return true
                ProbeStatus.NOT_FOUND -> return false
                ProbeStatus.UNKNOWN -> {
                    if (attempt < retries - 1) delay(1500L * (attempt + 1))
                }
            }
        }
        LOGGER.warning("Giving up on $urlStr after $retries attempts (rate-limited or blocked)")
        return false
    }

    // legacy scheme this app's downloader uses: zoom 7, jpg, 128x128 grid
    private suspend fun probeLegacy(version: String) = probeUrl("https://fortnite.gg/maps/$version/7/0/0.jpg")

    // newer scheme fortnite.gg has started serving very recent maps under: zoom 1, webp
    private suspend fun probeNew(version: String) = probeUrl("https://fortnite.gg/maps/$version/1/0/0.webp")

    private suspend fun probeVersion(version: String): ScanResult? {
        val legacy = probeLegacy(version)
        val new = if (!legacy) probeNew(version) else false
        return if (legacy || new) ScanResult(version) else null
    }

    private fun tileUrl(version: String, zoom: Int, x: Int, y: Int, ext: String) =
        "https://fortnite.gg/maps/$version/$zoom/$x/$y.$ext"

    // Determines the actual zoom level, grid size, and file extension a version serves tiles
    // under. Legacy versions serve full-res jpg at zoom 7 (128x128 grid). Newer versions only
    // serve webp - observed so far always at the same zoom/grid conventions as legacy (zoom 7,
    // 128x128), but we verify the full grid (not just the corner tile) and walk zoom levels
    // down instead of assuming, in case a future version caps out at a lower resolution.
    suspend fun detectTileScheme(version: String): TileScheme? {
        if (probeUrl(tileUrl(version, 7, 0, 0, "jpg"))) {
            return TileScheme(zoom = 7, gridSize = 128, extension = "jpg")
        }
        delay(300)

        for (zoom in 7 downTo 0) {
            val gridSize = 1 shl zoom
            val cornerExists = probeUrl(tileUrl(version, zoom, 0, 0, "webp"))
            delay(300)
            if (!cornerExists) continue

            val farCornerExists = probeUrl(tileUrl(version, zoom, gridSize - 1, gridSize - 1, "webp"))
            delay(300)
            if (farCornerExists) {
                return TileScheme(zoom = zoom, gridSize = gridSize, extension = "webp")
            }
        }
        return null
    }

    private suspend fun scanRange(
        major: Int,
        minors: IntRange,
        maxConsecutiveMisses: Int,
        checked: IntArray,
        onProgress: ((version: String, checked: Int) -> Unit)?,
        onFound: ((ScanResult) -> Unit)?,
        results: MutableList<ScanResult>
    ) {
        var consecutiveMisses = 0
        for (mi in minors) {
            val version = "$major.${mi.toString().padStart(2, '0')}"
            checked[0]++
            onProgress?.invoke(version, checked[0])
            val result = probeVersion(version)
            if (result != null) {
                results.add(result)
                onFound?.invoke(result)
                consecutiveMisses = 0
            } else {
                consecutiveMisses++
                if (consecutiveMisses >= maxConsecutiveMisses) break
            }
            delay(300)
        }
    }

    // Probes candidate versions after afterVersion (e.g. "40.02"). Fully sequential with spacing
    // between requests to stay well under fortnite.gg's rate limiting (no concurrent bursts).
    // Scans the next major version(s) FIRST with a tight range (new seasons are most likely to
    // show up there, so real finds surface within the first ~10-20 requests instead of after a
    // long sweep), then goes back and fills in the rest of the current major version. Stops early
    // within any range after `maxConsecutiveMisses` confirmed-not-found candidates in a row.
    // `onFound` fires immediately per hit, so callers can update UI incrementally instead of
    // waiting for the whole (potentially slow) scan to finish.
    suspend fun scanForNewVersions(
        afterVersion: String,
        majorsAhead: Int = 2,
        maxConsecutiveMisses: Int = 10,
        onProgress: ((version: String, checked: Int) -> Unit)? = null,
        onFound: ((ScanResult) -> Unit)? = null
    ): List<ScanResult> {
        val parts = afterVersion.split(".")
        val major = parts[0].toIntOrNull() ?: return emptyList()
        val minor = parts.getOrNull(1)?.toIntOrNull() ?: 0

        val results = mutableListOf<ScanResult>()
        val checked = intArrayOf(0)

        // next major version(s): most likely spot for the newest content, checked first
        for (m in (major + 1)..(major + majorsAhead)) {
            scanRange(m, 0..29, minOf(maxConsecutiveMisses, 6), checked, onProgress, onFound, results)
        }

        // remainder of the current major version, checked last
        scanRange(major, (minor + 1)..59, maxConsecutiveMisses, checked, onProgress, onFound, results)

        return results.sortedBy { it.version }
    }
}
