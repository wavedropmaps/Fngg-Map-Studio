package de.wauhundeland.fnggmapdownloader

import kotlinx.coroutines.DelicateCoroutinesApi
import kotlinx.coroutines.GlobalScope
import kotlinx.coroutines.launch
import java.awt.Graphics2D
import java.awt.Image
import java.awt.image.BufferedImage
import java.io.File
import java.net.URL
import java.util.concurrent.Semaphore
import java.util.logging.Logger
import javax.imageio.ImageIO

val LOGGER: Logger = Logger.getLogger("FNGGDownloader")
val baseDir = System.getProperty("user.home") + "/FNGGMapDownloader/"

class FNGGDownloader(val version: String) {
    private val rows = 128 // number of rows for final image
    private val cols = 128 // number of columns for final image
    private val width = 256 // width of each image
    private val height = 256 // height of each image

    private val tileSize = 64 // size of each tile in number of images
    private val tileWidth = width * tileSize // width of each tile in pixels
    private val tileHeight = height * tileSize // height of each tile in pixels

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
        var downloadedImages = 0 // number of images downloaded so far
        var lastProgress = 0
        var isCancelled = false
        for (x in 0 until 128) {
            for (y in 0 until 128) {
                val file = File("${baseDir}v$version/images/$x/$y.jpg")
                if (file.exists()) {
                    downloadedImages++
                    LOGGER.info("Image already exists: $downloadedImages/16384 images (${downloadedImages * 100 / 16384}%) (v$version)")
                    // only trigger progress callback on integer progress updates
                    val progress = downloadedImages * 100 / 16384
                    if (progress != lastProgress) {
                        progressCallback(progress.toFloat())
                        lastProgress = progress
                    }
                    continue
                }
                GlobalScope.launch {
                    if (isCancelled) {
                        return@launch
                    }
                    val file = File("${baseDir}v$version/images/$x/$y.jpg")
                    val url = "https://fortnite.gg/maps/$version/7/$x/$y.jpg"
                    val connection = URL(url).openConnection()
                    connection.setRequestProperty("User-Agent", "Mozilla/5.0")
                    val inputStream = connection.getInputStream()
                    file.parentFile.mkdirs()

                    file.createNewFile()
                    file.outputStream().use { outputStream ->
                        inputStream.copyTo(outputStream)
                    }
                    downloadedImages++
                    LOGGER.info("Downloaded $downloadedImages/16384 images (${downloadedImages * 100 / 16384}%) (v$version)")
                    // only trigger progress callback on integer progress updates
                    val progress = downloadedImages * 100 / 16384
                    if (progress != lastProgress) {
                        isCancelled = !progressCallback(progress.toFloat())
                        lastProgress = progress
                    }
                }
            }
        }

        // wait for all images to be downloaded
        while (downloadedImages < 16384) {
            Thread.sleep(500)
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

        val finalImage = BufferedImage(downscaledTileWidth * cols, downscaledTileHeight * rows, BufferedImage.TYPE_INT_RGB)
        val g: Graphics2D = finalImage.createGraphics()
        // fill background with pink color
        g.color = java.awt.Color.PINK
        g.fillRect(0, 0, downscaledTileWidth * cols, downscaledTileHeight * rows)

        var tilesProcessed = 0
        val totalTiles = rows * cols
        var lastProgress = 0

        for (tileCol in 0 until cols) {
            for (tileRow in 0 until rows) {
                val tileFile = File("${baseDir}v$version/images/$tileCol/$tileRow.jpg")
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