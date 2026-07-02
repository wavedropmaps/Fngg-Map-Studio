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
import de.wauhundeland.fnggmapdownloader.VersionScanner
import kotlinx.coroutines.*
import java.awt.Button

import java.awt.Desktop
import java.io.File
import java.io.InputStream
import java.net.URL

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
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
    var isScanningMaps by remember { mutableStateOf(false) }
    val bundledVersions = remember {
        val stream = object {}::class.java.classLoader.getResourceAsStream("maps_list.txt")
        stream?.bufferedReader()?.readLines()
            ?.map { File(it).nameWithoutExtension }
            ?: emptyList()
    }
    val recentVersionsFile = remember { File(System.getProperty("user.home") + "/FNGGMapDownloader/recent_versions.txt") }

    fun loadRecentVersions(): List<VersionScanner.ScanResult>? {
        if (!recentVersionsFile.exists()) return null
        val versions = recentVersionsFile.readLines().filter { it.isNotBlank() }
        return versions.map { VersionScanner.ScanResult(it) }.ifEmpty { null }
    }

    fun saveRecentVersions(versions: List<VersionScanner.ScanResult>) {
        recentVersionsFile.parentFile?.mkdirs()
        recentVersionsFile.writeText(versions.joinToString("\n") { it.version })
    }

    var recentVersions by remember {
        mutableStateOf(
            loadRecentVersions()
                ?: bundledVersions.takeLast(5).reversed().map { VersionScanner.ScanResult(it) }
        )
    }
    var isScanningVersions by remember { mutableStateOf(false) }
    var scannedVersions by remember { mutableStateOf<List<VersionScanner.ScanResult>>(emptyList()) }
    var scanMessage by remember { mutableStateOf<String?>(null) }

    // Function to scan for finished maps
    fun scanFinishedMaps() {
        if (isScanningMaps) return
        
        isScanningMaps = true
        scope.launch(Dispatchers.IO) {
            val newFinishedMaps = mutableListOf<String>()
            val baseDir = File(System.getProperty("user.home") + "/FNGGMapDownloader/")
            if (baseDir.exists()) {
                // scan all subfolders starting with v if they contain a file named "finalImage.png"
                baseDir.listFiles()?.forEach { versionDir ->
                    if (versionDir.isDirectory && versionDir.name.startsWith("v")) {
                        val finalImage = File("${versionDir.absolutePath}/finalImage.png")
                        if (finalImage.exists()) {
                            newFinishedMaps.add(finalImage.absolutePath)
                        }
                    }
                }
            }
            
            withContext(Dispatchers.Main) {
                finishedMaps.clear()
                finishedMaps.addAll(newFinishedMaps)
                finishedMapsScanned = true
                isScanningMaps = false
            }
        }
    }

    // Initial scan on first load
    LaunchedEffect(Unit) {
        if (!finishedMapsScanned) {
            scanFinishedMaps()
        }
    }

    // Function to download map preview. Legacy versions serve a jpg thumbnail; newer versions
    // only serve webp, so jpg is tried first and webp is the fallback.
    fun downloadMapPreview(mapNumber: String, onDownloaded: (ImageBitmap) -> Unit) {
        job = scope.launch(Dispatchers.IO) {
            for (ext in listOf("jpg", "webp")) {
                val inputStream = try {
                    val connection = URL("https://fortnite.gg/maps/$mapNumber/0/0/0.$ext").openConnection()
                    connection.connect()
                    connection.getInputStream()
                } catch (e: Exception) {
                    null
                }
                if (inputStream != null) {
                    val bitmap = loadImageBitmap(inputStream)
                    onDownloaded(bitmap)
                    loading = false
                    return@launch
                }
            }
            loading = false
            dlFailed = true
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
        val mapPreviewStream = bundledMapPreviewStream(debouncedVersion)
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
                val mapPreviewStream = bundledMapPreviewStream(version)
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
                    if (recentVersions.isNotEmpty()) {
                        FlowRow(
                            modifier = Modifier.padding(top = 4.dp).fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(4.dp),
                            verticalArrangement = Arrangement.spacedBy(4.dp)
                        ) {
                            recentVersions.forEach { entry ->
                                OutlinedButton(
                                    onClick = { version = entry.version },
                                    enabled = !isDownloading,
                                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 4.dp)
                                ) {
                                    Text(
                                        entry.version,
                                        style = MaterialTheme.typography.caption
                                    )
                                }
                            }
                        }
                    }
                    Row(
                        modifier = Modifier.padding(top = 4.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Button(
                            onClick = {
                                scope.launch(Dispatchers.IO) {
                                    isScanningVersions = true
                                    scanMessage = "Starting scan..."
                                    scannedVersions = emptyList()
                                    val latestKnown = recentVersions.firstOrNull()?.version ?: "0.0"
                                    val found = VersionScanner.scanForNewVersions(
                                        latestKnown,
                                        onProgress = { checkingVersion, checked ->
                                            scanMessage = "Checking $checkingVersion... ($checked checked)"
                                        },
                                        onFound = { result ->
                                            scannedVersions = (scannedVersions + result).sortedBy { it.version }
                                        }
                                    )
                                    scanMessage = if (found.isEmpty()) "No new versions found after $latestKnown" else "Scan complete"
                                    if (found.isNotEmpty()) {
                                        val bundledEntries = bundledVersions.map { VersionScanner.ScanResult(it) }
                                        recentVersions = (bundledEntries + found)
                                            .distinctBy { it.version }
                                            .sortedByDescending { it.version }
                                            .take(5)
                                        saveRecentVersions(recentVersions)
                                    }
                                    isScanningVersions = false
                                }
                            },
                            enabled = !isScanningVersions && !isDownloading,
                            contentPadding = PaddingValues(horizontal = 8.dp, vertical = 4.dp)
                        ) {
                            if (isScanningVersions) {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(14.dp),
                                    strokeWidth = 2.dp,
                                    color = MaterialTheme.colors.onPrimary
                                )
                            } else {
                                Text("Scan for new maps", style = MaterialTheme.typography.caption)
                            }
                        }
                        scanMessage?.let {
                            Text(it, style = MaterialTheme.typography.caption, modifier = Modifier.padding(start = 8.dp))
                        }
                    }
                    Row(modifier = Modifier.padding(top = 8.dp)) {
                        Button(
                            onClick = {
                                dlScope = scope.launch(Dispatchers.IO) {
                                    isDownloading = true
                                    val downloader = FNGGDownloader(version)
                                    progressIsInderteminate = true
                                    progressPercentage = 0f
                                    status = "Detecting map format..."
                                    try {
                                        downloader.detectScheme()
                                    } catch (e: Exception) {
                                        status = "Failed: ${e.message}"
                                        isDownloading = false
                                        return@launch
                                    }
                                    if (!isActive) return@launch
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
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text("Finished Maps", style = MaterialTheme.typography.h4)
                Button(
                    onClick = { scanFinishedMaps() },
                    enabled = !isScanningMaps,
                    modifier = Modifier.padding(start = 8.dp)
                ) {
                    if (isScanningMaps) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(16.dp),
                            strokeWidth = 2.dp
                        )
                    } else {
                        Text("Refresh")
                    }
                }
            }
            
            if (isScanningMaps && finishedMaps.isEmpty()) {
                Box(
                    modifier = Modifier.fillMaxWidth().padding(16.dp),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator()
                }
            } else if (finishedMaps.isNotEmpty()) {
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
            } else if (!isScanningMaps) {
                Text(
                    "No finished maps found. Download a map to see it here.",
                    modifier = Modifier.padding(vertical = 16.dp)
                )
            }
        }
    }
}

fun loadImageBitmap(inputStream: InputStream): ImageBitmap {
    return inputStream.buffered().use(::loadImageBitmap)
}

// Bundled preview thumbnails are jpg for legacy versions, webp for newer ones - try both.
fun bundledMapPreviewStream(version: String): InputStream? {
    val classLoader = object {}::class.java.classLoader
    return classLoader.getResourceAsStream("maps/$version.jpg")
        ?: classLoader.getResourceAsStream("maps/$version.webp")
}

fun main() = application {
    val icon = painterResource("icon.png")
    Window(onCloseRequest = ::exitApplication, icon = icon, title = "FNGG Map Downloader") {
        MainScreen()
    }
}
