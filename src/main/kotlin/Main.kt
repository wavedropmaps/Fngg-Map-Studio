import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.desktop.ui.tooling.preview.Preview
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.res.loadImageBitmap
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import de.wauhundeland.fnggmapdownloader.FNGGDownloader
import kotlinx.coroutines.*
import java.awt.Button

import java.awt.Desktop
import java.io.File
import java.io.InputStream
import java.net.URL

@Composable
@Preview
fun MainScreen() {
    var version by remember { mutableStateOf("28.10") }
    var debouncedVersion by remember { mutableStateOf(version) }
    var status by remember { mutableStateOf("Enter the map version and click Download") }
    val scope = rememberCoroutineScope()
    val scrollState = rememberScrollState()
    var selectedMapPreview by remember { mutableStateOf<ImageBitmap?>(null) }
    var dlFailed by remember { mutableStateOf(false) }
    var loading by remember { mutableStateOf(false) }
    var isDownloading by remember { mutableStateOf(false) }
    var progressIsInderteminate by remember { mutableStateOf(false) }
    var progressPercentage by remember { mutableStateOf(0f) }
    var job by remember { mutableStateOf<Job?>(null) }
    var dlScope by remember { mutableStateOf<Job?>(null) }
    var finishedPath by remember { mutableStateOf<File?>(null) }
    var finishedMap by remember { mutableStateOf<String?>(null) }
    val finishedMaps by remember { mutableStateOf(mutableListOf<String>()) }
    var finishedMapsScanned by remember { mutableStateOf(false) }

    if (!finishedMapsScanned) {
        finishedMaps.clear()
        val baseDir = File(System.getProperty("user.home") + "/FNGGMapDownloader/")
        if (baseDir.exists()) {
            // scan all subfolders starting with v if they contain a file named "finalImage.png"
            baseDir.listFiles()?.forEach { versionDir ->
                if (versionDir.isDirectory && versionDir.name.startsWith("v")) {
                    val finalImage = File("${versionDir.absolutePath}/finalImage.png")
                    if (finalImage.exists()) {
                        finishedMaps.add(finalImage.absolutePath)
                    }
                }
            }
        }
        finishedMapsScanned = true
    }

    // Function to download map preview
    fun downloadMapPreview(mapNumber: String, onDownloaded: (ImageBitmap) -> Unit) {
        job = scope.launch(Dispatchers.IO) {
            val url = URL("https://fortnite.gg/maps/$mapNumber/0/0/0.jpg")
            val connection = url.openConnection()
            connection.connect()
            val inputStream: InputStream
            try {
                inputStream = connection.getInputStream()
            } catch (e: Exception) {
                loading = false
                dlFailed = true
                return@launch
            }
            val bitmap = loadImageBitmap(inputStream)
            onDownloaded(bitmap)
            loading = false
        }
    }

    LaunchedEffect(version) {
        // ensure loading is true when not already loading
        if (!loading) {
            loading = true
        }
        delay(300) // Debounce delay
        debouncedVersion = version
    }

    LaunchedEffect(debouncedVersion) {
        job?.cancel()
        selectedMapPreview = null
        dlFailed = false
        loading = true
        val mapPreviewStream = object {}::class.java.classLoader.getResourceAsStream("maps/$debouncedVersion.jpg")
        if (mapPreviewStream != null) {
            selectedMapPreview = loadImageBitmap(mapPreviewStream)
            loading = false
        } else {
            try {
                downloadMapPreview(debouncedVersion) { bitmap ->
                    selectedMapPreview = bitmap
                }
            } catch (e: Exception) {
                selectedMapPreview = null
                dlFailed = true
                loading = false
            }
        }
    }

    // Box to contain sidebar and main content
    Box(Modifier.fillMaxSize()) {
        // Sidebar with all available maps
        Sidebar(
            updateCallback = { map ->
                version = map.nameWithoutExtension
                val mapPreviewStream = object {}::class.java.classLoader.getResourceAsStream("maps/$version.jpg")
                if (mapPreviewStream != null) {
                    selectedMapPreview = loadImageBitmap(mapPreviewStream)
                } else {
                    downloadMapPreview(map.nameWithoutExtension) { bitmap ->
                        selectedMapPreview = bitmap
                    }
                }
            },
            isDownloading
        )
        // Main content
        Column(
            Modifier
                .fillMaxSize()
                .padding(start = 220.dp, top = 16.dp, end = 16.dp, bottom = 16.dp)
                .verticalScroll(scrollState)
        ) {
            Text("Map Downloader", style = MaterialTheme.typography.h4)
            Row(
                verticalAlignment = Alignment.CenterVertically, modifier =
                Modifier
                    .fillMaxWidth()
                    .padding(bottom = 8.dp)
            ) {
                Column(Modifier.weight(1f)) {
                    TextField(
                        value = version,
                        onValueChange = { newVersion ->
                            version = newVersion
                        },
                        label = { Text("Map Version") },
                        enabled = !isDownloading,
                        modifier = Modifier.fillMaxWidth()
                    )
                    Row(modifier = Modifier.padding(top = 8.dp)) {
                        Button(
                            onClick = {
                                dlScope = scope.launch(Dispatchers.IO) {
                                    isDownloading = true
                                    val downloader = FNGGDownloader(version)
                                    progressIsInderteminate = true
                                    progressPercentage = 0f
                                    status = "Downloading images..."
                                    downloader.createBaseDir()
                                    downloader.downloadImages(progressCallback = { progress ->
                                        if (!isActive) return@downloadImages false
                                        progressPercentage = progress
                                        progressIsInderteminate = false
                                        status = "Downloading images... ($progress%)"
                                        return@downloadImages true
                                    })
                                    if (!isActive) return@launch
                                    progressIsInderteminate = true
                                    progressPercentage = 0f
                                    status = "Merging images..."
                                    val finalImage = downloader.mergeImages(progressCallback = { progress ->
                                        if (!isActive) return@mergeImages
                                        if (progress == -1f) {
                                            status = "Creating final image..."
                                            progressIsInderteminate = true
                                        } else {
                                            progressPercentage = progress
                                            status = "Merging images... ($progress%)"
                                            progressIsInderteminate = false
                                        }
                                    })
                                    if (!isActive) return@launch
                                    if (Desktop.isDesktopSupported() && Desktop.getDesktop()
                                            .isSupported(Desktop.Action.OPEN)
                                    ) {
                                        Desktop.getDesktop().open(finalImage)
                                    }
                                    finishedPath = finalImage
                                    status = "Done!"
                                    finishedMap = version
                                    isDownloading = false
                                    finishedMapsScanned = false
                                }
                            }, enabled = !isDownloading && !loading && !dlFailed
                        ) {
                            Text("Download")
                        }
                        if (isDownloading) {
                            Button(
                                onClick = {
                                    dlScope?.cancel()
                                    isDownloading = false
                                    status = "Download cancelled"
                                },
                                enabled = isDownloading,
                                modifier = Modifier.padding(start = 8.dp)
                            ) {
                                Text("Cancel")
                            }
                        }
                        if (finishedPath != null && !isDownloading) {
                            Button(
                                onClick = {
                                    if (Desktop.isDesktopSupported() && Desktop.getDesktop()
                                            .isSupported(Desktop.Action.OPEN)
                                    ) {
                                        Desktop.getDesktop().open(finishedPath)
                                    }
                                },
                                modifier = Modifier.padding(start = 8.dp)
                            ) {
                                Text("Open Map $finishedMap")
                            }
                        }
                    }
                    Text(status, modifier = Modifier.padding(top = 8.dp))
                    if (isDownloading) {
                        // progress bar
                        if (progressIsInderteminate) {
                            LinearProgressIndicator(
                                modifier = Modifier.fillMaxWidth()
                            )
                        } else {
                            LinearProgressIndicator(
                                progress = progressPercentage / 100f,
                                modifier = Modifier.fillMaxWidth()
                            )
                        }
                    }
                }
                if (selectedMapPreview == null) {
                    Box(
                        modifier = Modifier
                            .padding(start = 8.dp)
                            .size(150.dp)
                            .background(Color.LightGray)
                    ) {
                        if (!dlFailed) {
                            CircularProgressIndicator(
                                modifier = Modifier.align(Alignment.Center),
                                color = MaterialTheme.colors.primary
                            )
                        } else {
                            Text("Failed to load preview", modifier = Modifier.align(Alignment.Center))
                        }
                    }
                }
                selectedMapPreview?.let {
                    Image(
                        bitmap = it,
                        contentDescription = "Selected Map Preview",
                        modifier = Modifier
                            .padding(start = 8.dp)
                            .size(150.dp)
                            .background(Color.LightGray)
                    )
                }
            }

            // finished maps list
            if (finishedMaps.isNotEmpty()) {
                Text("Finished Maps", style = MaterialTheme.typography.h4)
                finishedMaps.forEach { map ->
                    Row(
                        modifier = Modifier.padding(bottom = 1.dp).fillMaxWidth()
                    )
                    {
                        Button(
                            onClick = {
                                if (Desktop.isDesktopSupported() && Desktop.getDesktop()
                                        .isSupported(Desktop.Action.OPEN)
                                ) {
                                    Desktop.getDesktop().open(File(map))
                                }
                            },
                            modifier = Modifier.fillMaxWidth().weight(1f),
                            colors = ButtonDefaults.buttonColors(backgroundColor = Color.LightGray)
                        ) {
                            Text("Open HQ Map " + File(map).parentFile.name)
                        }
                        Button (
                            onClick = {
                                if (Desktop.isDesktopSupported() && Desktop.getDesktop()
                                        .isSupported(Desktop.Action.OPEN)
                                ) {
                                    Desktop.getDesktop().open(File(map).parentFile)
                                }
                            },
                            modifier = Modifier.fillMaxWidth().weight(1f).padding(start = 8.dp),
                            colors = ButtonDefaults.buttonColors(backgroundColor = Color.LightGray)
                        ) {
                            Text("Open Folder for Map " + File(map).parentFile.name)
                        }
                    }
                }
            }
        }
    }
}

fun loadImageBitmap(inputStream: InputStream): ImageBitmap {
    return inputStream.buffered().use(::loadImageBitmap)
}

fun main() = application {
    val icon = painterResource("icon.png")
    Window(onCloseRequest = ::exitApplication, icon = icon, title = "FNGG Map Downloader") {
        MainScreen()
    }
}
