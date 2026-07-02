package de.wauhundeland.fnggmapdownloader

import kotlinx.coroutines.DelicateCoroutinesApi
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.GlobalScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import java.awt.Graphics2D
import java.awt.Image
import java.awt.image.BufferedImage
import java.io.File
import java.net.URL
import java.util.logging.Logger
import javax.imageio.ImageIO

val LOGGER: Logger = Logger.getLogger("FNGGDownloader")
val baseDir = System.getProperty("user.home") + "/FNGGMapDownloader/"

class FNGGDownloader(val version: String) {
    private val width = 256 // width of each tile image
    private val height = 256 // height of each tile image

    // Defaults match the legacy scheme; detectScheme() overwrites these once the actual
    // scheme for this version is known.
    private var zoomLevel = 7
    private var gridSize = 128
    private var extension = "jpg"

    // Figures out whether this version serves legacy full-res jpg tiles or the newer webp-only
    // scheme, and at what zoom/grid size, so downloadImages()/mergeImages() pull whichever
    // scheme this version actually has instead of assuming zoom 7/jpg/128x128.
    suspend fun detectScheme() {
        val scheme = VersionScanner.detectTileScheme(version)
            ?: throw Exception("No usable map tiles found for version $version")
        zoomLevel = scheme.zoom
        gridSize = scheme.gridSize
        extension = scheme.extension
        LOGGER.info("Detected tile scheme for v$version: zoom=$zoomLevel grid=$gridSize ext=$extension")
    }

    fun checkVersion() {
        // check if version exists by doing request to https://fortnite.gg/maps/$version and check if it does not return 404
        val url = "https://fortnite.gg/maps/$version"
        val connection = URL(url).openConnection()
        connection.setRequestProperty("User-Agent", "Mozilla/5.0")
        connection.connect()
        val responseCode = connection.getHeaderField(0) ?: "good response"
        LOGGER.info("Response code: $responseCode (v$version)")
        if (responseCode.contains("404")) {
            throw Exception("Map version $version does not exist")
        }
    }

    fun createBaseDir() {
        // create base directory if it does not exist
        val baseDirFile = File(baseDir)
        if (!baseDirFile.exists()) {
            baseDirFile.mkdir()
        }

        // create version directory if it does not exist
        val versionDir = File("${baseDir}v$version")
        if (!versionDir.exists()) {
            versionDir.mkdir()
        }

        // create images directory if it does not exist
        val imagesDir = File("${baseDir}v$version/images")
        if (!imagesDir.exists()) {
            imagesDir.mkdir()
        }

        // create tiles directory if it does not exist
        val tilesDir = File("${baseDir}v$version/tiles")
        if (!tilesDir.exists()) {
            tilesDir.mkdir()
        }
    }

    @OptIn(DelicateCoroutinesApi::class)
    fun downloadImages(progressCallback: (Float) -> Boolean) {
        // HttpURLConnection defaults to 5 concurrent connections per host, which serializes
        // most of the tile grid regardless of how many coroutines are in flight. Raise it so
        // the concurrency limit below is the actual bottleneck.
        System.setProperty("http.maxConnections", "64")

        val totalImages = gridSize * gridSize
        val downloadedImages = java.util.concurrent.atomic.AtomicInteger(0)
        var lastProgress = 0
        var isCancelled = false

        // Caps how many tiles download at once. Dispatchers.IO can schedule far more threads
        // than this, but an unbounded fan-out just floods the server and trips rate limiting.
        val concurrencyLimit = Semaphore(48)

        // Create a list to track download jobs
        val jobs = mutableListOf<Job>()

        for (x in 0 until gridSize) {
            for (y in 0 until gridSize) {
                val file = File("${baseDir}v$version/images/$x/$y.$extension")
                if (file.exists()) {
                    val currentCount = downloadedImages.incrementAndGet()
                    LOGGER.info("Image already exists: $currentCount/$totalImages images (${currentCount * 100 / totalImages}%) (v$version)")
                    // only trigger progress callback on integer progress updates
                    val progress = currentCount * 100 / totalImages
                    if (progress != lastProgress) {
                        progressCallback(progress.toFloat())
                        lastProgress = progress
                    }
                    continue
                }
                
                val job = GlobalScope.launch(Dispatchers.IO) {
                    if (isCancelled) {
                        return@launch
                    }

                    concurrencyLimit.withPermit {
                        try {
                            val file = File("${baseDir}v$version/images/$x/$y.$extension")
                            val url = "https://fortnite.gg/maps/$version/$zoomLevel/$x/$y.$extension"
                            val connection = URL(url).openConnection()
                            connection.setRequestProperty("User-Agent", "Mozilla/5.0")
                            connection.connectTimeout = 30000
                            connection.readTimeout = 30000
                            val inputStream = connection.getInputStream()
                            file.parentFile.mkdirs()

                            file.createNewFile()
                            file.outputStream().use { outputStream ->
                                inputStream.copyTo(outputStream)
                            }

                            val currentCount = downloadedImages.incrementAndGet()
                            LOGGER.info("Downloaded $currentCount/$totalImages images (${currentCount * 100 / totalImages}%) (v$version)")
                            // only trigger progress callback on integer progress updates
                            val progress = currentCount * 100 / totalImages
                            if (progress != lastProgress) {
                                // Update lastProgress in a synchronized way
                                synchronized(this) {
                                    if (progress != lastProgress) {
                                        isCancelled = !progressCallback(progress.toFloat())
                                        lastProgress = progress
                                    }
                                }
                            }
                        } catch (e: Exception) {
                            LOGGER.warning("Failed to download image ($x, $y): ${e.message}")
                            // Don't increment counter for failed downloads - they'll be retried
                            // Or we could increment to avoid hanging, but mark as failed
                            downloadedImages.incrementAndGet() // Increment anyway to prevent hanging
                        }
                    }
                }
                jobs.add(job)
            }
        }

        // Wait for all jobs to complete with timeout
        runBlocking {
            jobs.forEach { it.join() }
        }
        
        // Final check - if we have all images, ensure progress shows 100%
        if (downloadedImages.get() >= totalImages) {
            progressCallback(100f)
        }
    }

    fun mergeImages(progressCallback: (Float) -> Unit, downscaleFactor: Int = 2): File {
        val outputfile = File("${baseDir}v$version/finalImage.png")

        // if final image already exists, return it
        if (outputfile.exists()) {
            LOGGER.info("Final image already exists (v$version)")
            return outputfile
        }

        val downscaledTileWidth = width / downscaleFactor
        val downscaledTileHeight = height / downscaleFactor

        val finalImage = BufferedImage(downscaledTileWidth * gridSize, downscaledTileHeight * gridSize, BufferedImage.TYPE_INT_RGB)
        val g: Graphics2D = finalImage.createGraphics()
        // fill background with pink color
        g.color = java.awt.Color.PINK
        g.fillRect(0, 0, downscaledTileWidth * gridSize, downscaledTileHeight * gridSize)

        var tilesProcessed = 0
        val totalTiles = gridSize * gridSize
        var lastProgress = 0

        for (tileCol in 0 until gridSize) {
            for (tileRow in 0 until gridSize) {
                val tileFile = File("${baseDir}v$version/images/$tileCol/$tileRow.$extension")
                if (tileFile.exists()) {
                    val tileImage = ImageIO.read(tileFile)
                    if (tileImage != null) {
                        val downscaledTileImage = tileImage.getScaledInstance(downscaledTileWidth, downscaledTileHeight, Image.SCALE_SMOOTH)
                        g.drawImage(downscaledTileImage, tileCol * downscaledTileWidth, tileRow * downscaledTileHeight, null)
                    } else {
                        LOGGER.warning("Failed to read image: ${tileFile.absolutePath}")
                    }
                } else {
                    LOGGER.warning("Image file does not exist: ${tileFile.absolutePath}")
                }
                tilesProcessed++
                val progress = tilesProcessed * 100 / totalTiles
                if (progress != lastProgress) {
                    progressCallback(progress.toFloat())
                    lastProgress = progress
                }
            }
        }

        g.dispose()

        progressCallback(-1f)
        ImageIO.write(finalImage, "png", outputfile)
        LOGGER.info("Final image created (v$version)")

        return outputfile
    }
}