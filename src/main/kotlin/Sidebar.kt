import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.material.Button
import androidx.compose.material.MaterialTheme
import androidx.compose.material.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.res.loadImageBitmap
import androidx.compose.ui.unit.dp
import java.io.File
import java.io.InputStream
import java.util.zip.ZipInputStream

@Composable
fun Sidebar(
    updateCallback: (File) -> Unit,
    isDownloading: Boolean
) {
    val scrollState = rememberScrollState()
    val mapNameCache = remember { mutableListOf<String>() }
    val mapPreviews = remember { mutableMapOf<String, ImageBitmap?>() }

    // if mapnamecache is empty, read maps from maps_list.txt
    if (mapNameCache.isEmpty()) {
        val mapsListStream: InputStream? = object {}::class.java.classLoader.getResourceAsStream("maps_list.txt")
        if (mapsListStream != null) {
            val mapNames = mapsListStream.bufferedReader().readLines()
            mapNameCache.addAll(mapNames)
            println("Loaded ${mapNameCache.size} maps")
            // select last map by default
            if (mapNameCache.isNotEmpty()) {
                val lastMap = mapNameCache.last()
                val lastMapFile = File("maps/$lastMap")
                updateCallback(lastMapFile)
            }
        } else {
            println("maps_list.txt not found")
        }
    }

    Column(
        Modifier
            .fillMaxHeight()
            .width(200.dp)
            .background(Color.LightGray)
            .padding(16.dp)
            .verticalScroll(scrollState)
    ) {
        Text("Maps", style = MaterialTheme.typography.h6)

        // for each map in mapnamecache, create a preview
        mapNameCache.forEach { mapName ->
            val mapFile = File("maps/$mapName")
            val mapPreview = mapPreviews.getOrPut(mapName) {
                val mapPreviewStream = object {}::class.java.classLoader.getResourceAsStream("maps/$mapName")
                if (mapPreviewStream != null) {
                    loadImageBitmap(mapPreviewStream)
                } else {
                    println("Failed to load image: $mapName")
                    null
                }
            }
            if (mapPreview != null) {
                Button(
                    onClick = {
                        updateCallback(mapFile)
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 4.dp),
                    enabled = !isDownloading
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Image(
                            bitmap = mapPreview,
                            contentDescription = mapName.removeSuffix(".jpg"),
                            modifier = Modifier.fillMaxWidth()
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(mapName.removeSuffix(".jpg"))
                    }
                }
            }
        }
    }
}