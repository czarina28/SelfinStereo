<?php
declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
try {
    $q = $_GET['q'] ?? '';
    if (!is_string($q) || strlen($q)>240) { http_response_code(400); echo '[]'; exit; }
    preg_match_all('/[\p{L}\p{N}\p{M}]+/u', $q, $m);
    $words = array_slice($m[0] ?? [],0,8);
    if (mb_strlen(trim($q))<3 || !$words) { echo '[]'; exit; }
    $match = implode(' AND ',array_map(fn($w)=>'"'.$w.'"*',$words));
    $db = new SQLite3('/var/lib/music_catalog/music_catalog.sqlite',SQLITE3_OPEN_READONLY);
    $db->enableExceptions(true);
    $db->exec('PRAGMA query_only=ON');
    $stmt=$db->prepare("SELECT s.title,s.artist,s.mbid,s.variants FROM (SELECT rowid FROM songs_fts WHERE songs_fts MATCH :q LIMIT 3000) f JOIN songs s ON s.id=f.rowid ORDER BY s.variants DESC, length(s.title), s.title LIMIT 10");
    $stmt->bindValue(':q',$match,SQLITE3_TEXT);
    $result=$stmt->execute();
    $rows=[];
    while($row=$result->fetchArray(SQLITE3_ASSOC)) $rows[]=$row;
    echo json_encode($rows,JSON_UNESCAPED_UNICODE|JSON_INVALID_UTF8_SUBSTITUTE);
} catch(Throwable $e) {
    http_response_code(503);
    echo json_encode(['error'=>'Search unavailable']);
}
