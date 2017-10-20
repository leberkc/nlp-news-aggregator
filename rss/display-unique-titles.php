<html>
<body>
<style type="text/css">
th,td{
border-width:0px 1px 1px 0px;
}
</style>

<?php   
require_once("config.php");

$sql = "SELECT * FROM articles GROUP BY article_title";
#if($result = mysqli_query($link, $sql)){
if($result = mysqli_query($con,$sql)){
if(mysqli_num_rows($result) > 0){
    echo'<table border="1" ><th>ID</th><th>Title</th><th>Cluster ID</th><th>Rank</th><th>TimeStamp</th>';
#    echo "<table>";

    while($row = mysqli_fetch_array($result)){
       $url = $row  ['url'];
       echo "<tr>";
                       echo "<td>".$row ['id']."</td>  <td><a href='" . $url . "'>" . $row ['article_title'] . "</a></td>  <td> ". $row ['cluster_id'] ."<td> ". $row ['rank'] ."<td> ". $row ['timestamp'] . "</td>";
       echo "</tr>";
        }
        echo "</table>";
    } 
 } 
#mysqli_close($link);
mysqli_close($con);
?>
</body>
</html>
