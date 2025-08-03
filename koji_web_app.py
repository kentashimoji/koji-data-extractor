# -*- coding: utf-8 -*-
"""
電子公図データ抽出Webアプリ (Streamlit版)
"""

import streamlit as st
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon, MultiPolygon
import xml.etree.ElementTree as ET
from xml.dom import minidom
import zipfile
import io
import tempfile
import os

# ページ設定
st.set_page_config(
    page_title="電子公図データ抽出ツール",
    page_icon="🗺️",
    layout="wide"
)

class KojiWebExtractor:
    def __init__(self):
        if 'gdf' not in st.session_state:
            st.session_state.gdf = None
    
    def create_kml_from_geodataframe(self, gdf, name="地番データ"):
        """GeoPandasデータフレームからKMLファイルを作成（座標変換付き）"""
        try:
            # WGS84（緯度経度）に座標変換
            gdf_wgs84 = gdf.to_crs(epsg=4326)
            
            # KMLのルート要素を作成
            kml = ET.Element("kml", xmlns="http://www.opengis.net/kml/2.2")
            document = ET.SubElement(kml, "Document")
            doc_name = ET.SubElement(document, "name")
            doc_name.text = name
            
            # スタイルを定義
            style = ET.SubElement(document, "Style", id="PolygonStyle")
            line_style = ET.SubElement(style, "LineStyle")
            line_color = ET.SubElement(line_style, "color")
            line_color.text = "ff0000ff"  # 赤色
            line_width = ET.SubElement(line_style, "width")
            line_width.text = "2"
            
            poly_style = ET.SubElement(style, "PolyStyle")
            poly_color = ET.SubElement(poly_style, "color")
            poly_color.text = "3300ff00"  # 半透明緑
            
            # 各レコードに対してPlacemarkを作成
            for idx, row in gdf_wgs84.iterrows():
                placemark = ET.SubElement(document, "Placemark")
                
                # 名前を設定
                pm_name = ET.SubElement(placemark, "name")
                if '地番' in row:
                    pm_name.text = str(row['地番'])
                else:
                    pm_name.text = f"地番_{idx}"
                
                # 説明を設定
                description = ET.SubElement(placemark, "description")
                desc_text = ""
                for col in gdf_wgs84.columns:
                    if col != 'geometry':
                        desc_text += f"{col}: {row[col]}<br/>"
                description.text = desc_text
                
                # スタイルを適用
                style_url = ET.SubElement(placemark, "styleUrl")
                style_url.text = "#PolygonStyle"
                
                # ジオメトリを処理
                geom = row['geometry']
                if geom.geom_type == 'Polygon':
                    self._add_polygon_to_placemark(placemark, geom)
                elif geom.geom_type == 'MultiPolygon':
                    for poly in geom.geoms:
                        self._add_polygon_to_placemark(placemark, poly)
                elif geom.geom_type == 'Point':
                    self._add_point_to_placemark(placemark, geom)
            
            # XMLを整形して文字列として返す
            rough_string = ET.tostring(kml, 'unicode')
            reparsed = minidom.parseString(rough_string)
            pretty_xml = reparsed.toprettyxml(indent="  ")
            
            return pretty_xml
            
        except Exception as e:
            st.error(f"KML作成エラー: {str(e)}")
            return None
    
    def _add_polygon_to_placemark(self, placemark, polygon):
        """PolygonをPlacemarkに追加"""
        multigeometry = placemark.find("MultiGeometry")
        if multigeometry is None:
            multigeometry = ET.SubElement(placemark, "MultiGeometry")
        
        kml_polygon = ET.SubElement(multigeometry, "Polygon")
        
        # 外環を追加
        outer_boundary = ET.SubElement(kml_polygon, "outerBoundaryIs")
        linear_ring = ET.SubElement(outer_boundary, "LinearRing")
        coordinates = ET.SubElement(linear_ring, "coordinates")
        
        # 座標を文字列に変換
        coord_str = ""
        for x, y in polygon.exterior.coords:
            coord_str += f"{x},{y},0 "
        coordinates.text = coord_str.strip()
        
        # 内環がある場合は追加
        for interior in polygon.interiors:
            inner_boundary = ET.SubElement(kml_polygon, "innerBoundaryIs")
            inner_ring = ET.SubElement(inner_boundary, "LinearRing")
            inner_coordinates = ET.SubElement(inner_ring, "coordinates")
            
            inner_coord_str = ""
            for x, y in interior.coords:
                inner_coord_str += f"{x},{y},0 "
            inner_coordinates.text = inner_coord_str.strip()
    
    def _add_point_to_placemark(self, placemark, point):
        """PointをPlacemarkに追加"""
        kml_point = ET.SubElement(placemark, "Point")
        coordinates = ET.SubElement(kml_point, "coordinates")
        coordinates.text = f"{point.x},{point.y},0"
    
    def extract_data(self, gdf, oaza, chiban, range_m):
        """データ抽出処理"""
        try:
            # 指定した筆を検索
            df = gdf[(gdf['大字名'] == oaza) & (gdf['地番'] == chiban)]
            
            if df.empty:
                return None, None, "該当する筆が見つかりませんでした"
            
            # 不要な列を削除
            df_summary = df.reindex(columns=["大字名", "丁目名", "地番", "geometry"])
            
            # 中心点計算と周辺筆抽出
            cen = df_summary.centroid
            
            cen_gdf = gpd.GeoDataFrame(geometry=cen)
            cen_gdf['x'] = cen_gdf['geometry'].x
            cen_gdf['y'] = cen_gdf['geometry'].y
            
            # 検索範囲の4角ポイント計算
            i1 = cen_gdf['x'] + range_m
            i2 = cen_gdf['x'] - range_m
            i3 = cen_gdf['y'] + range_m
            i4 = cen_gdf['y'] - range_m
            
            x1, y1 = i3.iloc[0], i1.iloc[0]
            x2, y2 = i4.iloc[0], i2.iloc[0]
            
            # 4つのポイントを定義
            top_right = [x1, y1]
            lower_left = [x2, y2]
            lower_right = [x1, y2]
            top_left = [x2, y1]
            
            points = pd.DataFrame([top_right, lower_left, lower_right, top_left],
                                index=["top_right", "lower_left", "lower_right", "top_left"],
                                columns=["lon", "lat"])
            
            # ジオメトリ作成
            geometry = [Point(xy) for xy in zip(points.lat, points.lon)]
            four_points_gdf = gpd.GeoDataFrame(points, geometry=geometry)
            
            # 検索範囲のポリゴン作成
            sq = four_points_gdf.dissolve().convex_hull
            
            # オーバーレイ処理
            df1 = gpd.GeoDataFrame({'geometry': sq})
            df1 = df1.set_crs(gdf.crs)
            df2 = gpd.GeoDataFrame({'地番': gdf['地番'], 'geometry': gdf['geometry']})
            
            overlay_gdf = df1.overlay(df2, how='intersection')
            
            return df_summary, overlay_gdf, f"対象筆: {len(df_summary)}件, 周辺筆: {len(overlay_gdf)}件"
            
        except Exception as e:
            return None, None, f"エラー: {str(e)}"

def main():
    st.title("🗺️ 電子公図データ抽出ツール")
    st.markdown("---")
    
    extractor = KojiWebExtractor()
    
    # サイドバー
    st.sidebar.header("📂 ファイルアップロード")
    
    # ファイルアップロード
    uploaded_file = st.sidebar.file_uploader(
        "SHPファイルをアップロード",
        type=['zip'],
        help="SHPファイル一式をZIPで圧縮してアップロードしてください"
    )
    
    if uploaded_file is not None:
        try:
            # ZIPファイルを展開してSHPファイルを読み込み
            with tempfile.TemporaryDirectory() as temp_dir:
                # ZIPファイルを展開
                with zipfile.ZipFile(uploaded_file, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                
                # SHPファイルを探す
                shp_files = [f for f in os.listdir(temp_dir) if f.endswith('.shp')]
                
                if shp_files:
                    shp_path = os.path.join(temp_dir, shp_files[0])
                    st.session_state.gdf = gpd.read_file(shp_path)
                    
                    st.sidebar.success("✅ ファイル読み込み完了!")
                    st.sidebar.info(f"📊 レコード数: {len(st.session_state.gdf):,}件")
                    
                    # 座標参照系の確認
                    if st.session_state.gdf.crs:
                        st.sidebar.info(f"🗺️ 座標系: {st.session_state.gdf.crs}")
                else:
                    st.sidebar.error("❌ SHPファイルが見つかりません")
                    
        except Exception as e:
            st.sidebar.error(f"❌ ファイル読み込みエラー: {str(e)}")
    
    # メインエリア
    if st.session_state.gdf is not None:
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.header("🔍 検索条件")
            
            # 大字名選択
            oaza_list = sorted(st.session_state.gdf['大字名'].unique())
            selected_oaza = st.selectbox("大字名を選択", oaza_list)
            
            # 地番入力
            chiban = st.text_input("地番を入力", value="1174")
            
            # 検索範囲
            range_m = st.number_input("検索範囲 (m)", min_value=1, max_value=1000, value=61)
            
            # 抽出ボタン
            if st.button("🚀 データ抽出", type="primary", use_container_width=True):
                if selected_oaza and chiban:
                    with st.spinner("データ抽出中..."):
                        target_gdf, overlay_gdf, message = extractor.extract_data(
                            st.session_state.gdf, selected_oaza, chiban, range_m
                        )
                    
                    st.info(message)
                    
                    if target_gdf is not None and overlay_gdf is not None:
                        # 結果を保存
                        st.session_state.target_gdf = target_gdf
                        st.session_state.overlay_gdf = overlay_gdf
                        st.session_state.file_name = f"{selected_oaza}{chiban}"
                else:
                    st.error("大字名と地番を入力してください")
        
        with col2:
            st.header("📊 データ一覧")
            
            # 大字名のサマリー
            if st.checkbox("大字名一覧を表示"):
                oaza_summary = st.session_state.gdf['大字名'].value_counts()
                st.dataframe(oaza_summary.head(20), use_container_width=True)
            
            # 地番検索
            if st.checkbox("地番検索"):
                search_term = st.text_input("地番を検索", placeholder="例: 1174")
                if search_term:
                    filtered = st.session_state.gdf[
                        st.session_state.gdf['地番'].astype(str).str.contains(search_term, na=False)
                    ]
                    st.dataframe(
                        filtered[['大字名', '地番']].head(20),
                        use_container_width=True
                    )
        
        # 結果表示とダウンロード
        if 'target_gdf' in st.session_state and 'overlay_gdf' in st.session_state:
            st.markdown("---")
            st.header("📥 ダウンロード")
            
            col3, col4, col5 = st.columns(3)
            
            with col3:
                st.subheader("🎯 対象筆")
                target_kml = extractor.create_kml_from_geodataframe(
                    st.session_state.target_gdf, 
                    f"{st.session_state.file_name}_対象筆"
                )
                if target_kml:
                    st.download_button(
                        "📄 対象筆KMLダウンロード",
                        data=target_kml,
                        file_name=f"{st.session_state.file_name}_対象筆.kml",
                        mime="application/vnd.google-earth.kml+xml",
                        use_container_width=True
                    )
            
            with col4:
                st.subheader("🏘️ 周辺筆")
                overlay_kml = extractor.create_kml_from_geodataframe(
                    st.session_state.overlay_gdf,
                    f"{st.session_state.file_name}_周辺筆"
                )
                if overlay_kml:
                    st.download_button(
                        "📄 周辺筆KMLダウンロード",
                        data=overlay_kml,
                        file_name=f"{st.session_state.file_name}_周辺筆.kml",
                        mime="application/vnd.google-earth.kml+xml",
                        use_container_width=True
                    )
            
            with col5:
                st.subheader("📊 CSV出力")
                # 座標情報付きCSV
                csv_data = st.session_state.overlay_gdf.copy()
                csv_data['中心X座標'] = csv_data['geometry'].centroid.x
                csv_data['中心Y座標'] = csv_data['geometry'].centroid.y
                csv_export = csv_data.drop(columns=['geometry']).to_csv(index=False, encoding='shift-jis')
                
                st.download_button(
                    "📊 周辺筆CSVダウンロード",
                    data=csv_export,
                    file_name=f"{st.session_state.file_name}_周辺筆.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            
            # 結果プレビュー
            st.markdown("---")
            st.header("👀 結果プレビュー")
            
            tab1, tab2 = st.tabs(["対象筆", "周辺筆"])
            
            with tab1:
                if not st.session_state.target_gdf.empty:
                    display_df = st.session_state.target_gdf.drop(columns=['geometry'])
                    st.dataframe(display_df, use_container_width=True)
            
            with tab2:
                if not st.session_state.overlay_gdf.empty:
                    display_df = st.session_state.overlay_gdf.drop(columns=['geometry'])
                    st.dataframe(display_df, use_container_width=True)
    
    else:
        st.info("👆 SHPファイル（ZIP形式）をアップロードしてください")
        
        # 使い方説明
        with st.expander("📖 使い方"):
            st.markdown("""
            ### 📋 手順
            1. **SHPファイル一式をZIP圧縮**してアップロード
            2. **大字名**をドロップダウンから選択
            3. **地番**を入力
            4. **検索範囲**を設定（デフォルト: 61m）
            5. **データ抽出**ボタンをクリック
            6. **KMLファイル**をダウンロード
            
            ### 🎯 出力ファイル
            - **対象筆KML**: 指定した筆のKMLファイル
            - **周辺筆KML**: 周辺筆のKMLファイル
            - **CSV**: 座標情報付きのCSVファイル
            
            ### 🗺️ 対応ソフトウェア
            - Google Earth
            - Google マイマップ
            - QGIS
            - その他GISソフトウェア
            """)

if __name__ == "__main__":
    main()