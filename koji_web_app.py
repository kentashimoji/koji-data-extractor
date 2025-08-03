# -*- coding: utf-8 -*-
"""
電子公図データ抽出Webアプリ (Streamlit版) - Web/GitHub参照対応
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
import requests
from urllib.parse import urlparse

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
    
    def download_file_from_url(self, url):
        """URLからファイルをダウンロード"""
        try:
            # GitHubの生ファイルURLに変換
            if 'github.com' in url and '/blob/' in url:
                url = url.replace('github.com', 'raw.githubusercontent.com').replace('/blob/', '/')
            
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            return io.BytesIO(response.content)
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"ファイルのダウンロードに失敗しました: {str(e)}")
    
    def load_shapefile_from_url(self, url):
        """URLからShapefileを読み込み"""
        try:
            file_obj = self.download_file_from_url(url)
            
            with tempfile.TemporaryDirectory() as temp_dir:
                # ZIPファイルとして展開を試行
                try:
                    with zipfile.ZipFile(file_obj, 'r') as zip_ref:
                        zip_ref.extractall(temp_dir)
                    
                    # SHPファイルを探す
                    shp_files = [f for f in os.listdir(temp_dir) if f.endswith('.shp')]
                    
                    if shp_files:
                        shp_path = os.path.join(temp_dir, shp_files[0])
                        return gpd.read_file(shp_path)
                    else:
                        raise Exception("ZIPファイル内にSHPファイルが見つかりません")
                        
                except zipfile.BadZipFile:
                    # ZIPファイルでない場合、直接SHPファイルとして読み込みを試行
                    file_obj.seek(0)  # ファイルポインタをリセット
                    
                    # 一時的にファイルを保存
                    temp_file = os.path.join(temp_dir, "temp_file")
                    with open(temp_file, 'wb') as f:
                        f.write(file_obj.read())
                    
                    # 拡張子を推測してリネーム
                    if url.lower().endswith('.shp'):
                        shp_file = temp_file + '.shp'
                        os.rename(temp_file, shp_file)
                        return gpd.read_file(shp_file)
                    else:
                        return gpd.read_file(temp_file)
                        
        except Exception as e:
            raise Exception(f"Shapefileの読み込みに失敗しました: {str(e)}")
    
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
            # 必要な列の存在確認
            required_columns = ['大字名', '地番']
            missing_columns = [col for col in required_columns if col not in gdf.columns]
            
            if missing_columns:
                return None, None, f"必要な列が見つかりません: {missing_columns}"
            
            # NULL値をチェック
            null_check = {}
            for col in required_columns:
                null_count = gdf[col].isnull().sum()
                if null_count > 0:
                    null_check[col] = null_count
            
            if null_check:
                warning_msg = "警告: NULL値が含まれています - " + ", ".join([f"{k}: {v}件" for k, v in null_check.items()])
                st.warning(warning_msg)
            
            # 指定した筆を検索（NULL値を除外）
            search_condition = (
                (gdf['大字名'] == oaza) & 
                (gdf['地番'] == chiban) &
                (gdf['大字名'].notna()) &
                (gdf['地番'].notna())
            )
            
            df = gdf[search_condition]
            
            if df.empty:
                # デバッグ情報を提供
                debug_info = []
                oaza_matches = gdf[gdf['大字名'] == oaza]['大字名'].count()
                chiban_matches = gdf[gdf['地番'] == chiban]['地番'].count()
                
                debug_info.append(f"大字名'{oaza}'の該当件数: {oaza_matches}")
                debug_info.append(f"地番'{chiban}'の該当件数: {chiban_matches}")
                
                return None, None, f"該当する筆が見つかりませんでした。{' / '.join(debug_info)}"
            
            # 利用可能な列のみを選択
            available_columns = ["大字名", "地番", "geometry"]
            if "丁目名" in gdf.columns:
                available_columns.insert(1, "丁目名")
            
            # 存在する列のみでデータフレームを作成
            existing_columns = [col for col in available_columns if col in df.columns]
            df_summary = df.reindex(columns=existing_columns)
            
            # geometryカラムが存在し、有効かチェック
            if 'geometry' not in df_summary.columns:
                return None, None, "geometry列が見つかりません"
            
            if df_summary['geometry'].isnull().any():
                return None, None, "geometry列にNULL値が含まれています"
            
            # 中心点計算と周辺筆抽出
            cen = df_summary.geometry.centroid
            
            cen_gdf = gpd.GeoDataFrame(geometry=cen)
            cen_gdf['x'] = cen_gdf.geometry.x
            cen_gdf['y'] = cen_gdf.geometry.y
            
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
            
            # オーバーレイ処理（NULL値を除外したデータで）
            df1 = gpd.GeoDataFrame({'geometry': sq})
            df1 = df1.set_crs(gdf.crs)
            
            # 地番とgeometryが両方とも有効なデータのみを使用
            valid_data = gdf[(gdf['地番'].notna()) & (gdf['geometry'].notna())].copy()
            df2 = gpd.GeoDataFrame({'地番': valid_data['地番'], 'geometry': valid_data['geometry']})
            
            overlay_gdf = df1.overlay(df2, how='intersection')
            
            return df_summary, overlay_gdf, f"対象筆: {len(df_summary)}件, 周辺筆: {len(overlay_gdf)}件"
            
        except Exception as e:
            return None, None, f"エラー: {str(e)}"

def main():
    st.title("🗺️ 電子公図データ抽出ツール")
    st.markdown("---")
    
    extractor = KojiWebExtractor()
    
    # サイドバー
    st.sidebar.header("📂 データソース選択")
    
    # データソース選択
    data_source = st.sidebar.radio(
        "データソースを選択してください",
        ["📁 ローカルファイル", "🌐 Web URL", "🐙 GitHub"],
        help="データの取得方法を選択してください"
    )
    
    if data_source == "📁 ローカルファイル":
        # 従来のファイルアップロード
        uploaded_file = st.sidebar.file_uploader(
            "SHPファイルをアップロード",
            type=['zip'],
            help="SHPファイル一式をZIPで圧縮してアップロードしてください"
        )
        
        if uploaded_file is not None:
            try:
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
                        
                        # データソース情報を記録
                        st.session_state.data_source = "ローカルファイル"
                        st.session_state.file_info = uploaded_file.name
                    else:
                        st.sidebar.error("❌ SHPファイルが見つかりません")
                        
            except Exception as e:
                st.sidebar.error(f"❌ ファイル読み込みエラー: {str(e)}")
    
    elif data_source == "🌐 Web URL":
        # Web URL入力
        web_url = st.sidebar.text_input(
            "ファイルのURL",
            placeholder="https://example.com/data.zip",
            help="ZIPファイルまたはSHPファイルの直接URLを入力してください"
        )
        
        if st.sidebar.button("🌐 URLから読み込み", type="primary"):
            if web_url:
                try:
                    with st.spinner("URLからファイルを読み込み中..."):
                        st.session_state.gdf = extractor.load_shapefile_from_url(web_url)
                    
                    st.sidebar.success("✅ ファイル読み込み完了!")
                    st.sidebar.info(f"📊 レコード数: {len(st.session_state.gdf):,}件")
                    
                    if st.session_state.gdf.crs:
                        st.sidebar.info(f"🗺️ 座標系: {st.session_state.gdf.crs}")
                    
                    # データソース情報を記録
                    st.session_state.data_source = "GitHub"
                    st.session_state.file_info = github_url
                    
                    # データソース情報を記録
                    st.session_state.data_source = "Web URL"
                    st.session_state.file_info = web_url
                        
                except Exception as e:
                    st.sidebar.error(f"❌ {str(e)}")
            else:
                st.sidebar.error("URLを入力してください")
    
    elif data_source == "🐙 GitHub":
        # GitHub URL入力
        col_owner, col_repo = st.sidebar.columns(2)
        with col_owner:
            github_owner = st.text_input("GitHubユーザー名", placeholder="username")
        with col_repo:
            github_repo = st.text_input("リポジトリ名", placeholder="repository")
        
        github_path = st.sidebar.text_input(
            "ファイルパス",
            placeholder="data/shapefile.zip",
            help="リポジトリ内のファイルパスを入力してください"
        )
        
        github_branch = st.sidebar.text_input("ブランチ名", value="main")
        
        if st.sidebar.button("🐙 GitHubから読み込み", type="primary"):
            if github_owner and github_repo and github_path:
                try:
                    github_url = f"https://github.com/{github_owner}/{github_repo}/blob/{github_branch}/{github_path}"
                    
                    with st.spinner("GitHubからファイルを読み込み中..."):
                        st.session_state.gdf = extractor.load_shapefile_from_url(github_url)
                    
                    st.sidebar.success("✅ ファイル読み込み完了!")
                    st.sidebar.info(f"📊 レコード数: {len(st.session_state.gdf):,}件")
                    
                    if st.session_state.gdf.crs:
                        st.sidebar.info(f"🗺️ 座標系: {st.session_state.gdf.crs}")
                        
                except Exception as e:
                    st.sidebar.error(f"❌ {str(e)}")
            else:
                st.sidebar.error("GitHubの情報をすべて入力してください")
    
    # プリセットファイル機能
    with st.sidebar.expander("📋 プリセットファイル"):
        st.markdown("**よく使用するデータセット**")
        
        # プリセット設定（実際の使用時は設定ファイルやデータベースから読み込み）
        presets = {
            "🏙️ 東京都市部サンプル": {
                "url": "https://raw.githubusercontent.com/example/tokyo-data/main/tokyo_sample.zip",
                "description": "東京都心部の公図データサンプル"
            },
            "🌾 農村部サンプル": {
                "url": "https://raw.githubusercontent.com/example/rural-data/main/rural_sample.zip", 
                "description": "農村部の公図データサンプル"
            },
            "🏖️ 沖縄県データ": {
                "url": "https://raw.githubusercontent.com/okinawa-gis/public-data/main/okinawa_koji.zip",
                "description": "沖縄県の公図データ（仮想）"
            },
            "🗾 全国統合データ": {
                "url": "https://example.com/national_koji_data.zip",
                "description": "全国の公図データ統合版"
            }
        }
        
        # プリセット選択
        selected_preset = st.selectbox(
            "プリセットを選択",
            ["選択してください..."] + list(presets.keys()),
            help="事前に設定された地理データから選択できます"
        )
        
        if selected_preset != "選択してください...":
            preset_info = presets[selected_preset]
            st.info(f"📝 {preset_info['description']}")
            st.code(preset_info['url'], language="text")
            
            if st.button("🚀 プリセットデータを読み込み", type="primary"):
                try:
                    with st.spinner(f"{selected_preset}を読み込み中..."):
                        st.session_state.gdf = extractor.load_shapefile_from_url(preset_info['url'])
                    
                    st.success(f"✅ {selected_preset}を読み込み完了!")
                    st.info(f"📊 レコード数: {len(st.session_state.gdf):,}件")
                    
                    if st.session_state.gdf.crs:
                        st.info(f"🗺️ 座標系: {st.session_state.gdf.crs}")
                        
                    # プリセット名を記録
                    st.session_state.current_preset = selected_preset
                        
                except Exception as e:
                    st.error(f"❌ {str(e)}")
        
        st.markdown("---")
        
        # カスタムプリセット追加機能
        st.markdown("**カスタムプリセット追加**")
        
        # 追加方法の選択
        add_method = st.radio(
            "追加方法を選択",
            ["📝 個別追加", "📁 フォルダ一括追加", "🌐 URL一括追加"],
            horizontal=True
        )
        
        if add_method == "📝 個別追加":
            with st.form("add_preset_form"):
                new_preset_name = st.text_input("プリセット名", placeholder="例: 私の地域データ")
                new_preset_url = st.text_input("データURL", placeholder="https://...")
                new_preset_desc = st.text_area("説明", placeholder="このデータセットの説明...")
                
                if st.form_submit_button("➕ プリセットに追加"):
                    if new_preset_name and new_preset_url:
                        # セッション状態にカスタムプリセットを保存
                        if 'custom_presets' not in st.session_state:
                            st.session_state.custom_presets = {}
                        
                        st.session_state.custom_presets[f"🔧 {new_preset_name}"] = {
                            "url": new_preset_url,
                            "description": new_preset_desc or "カスタムデータセット"
                        }
                        
                        st.success(f"✅ '{new_preset_name}'をプリセットに追加しました")
                        st.rerun()
                    else:
                        st.error("プリセット名とURLは必須です")
        
        elif add_method == "📁 フォルダ一括追加":
            with st.form("folder_preset_form"):
                st.markdown("**フォルダベースURL設定**")
                base_url = st.text_input(
                    "ベースURL", 
                    placeholder="https://example.com/data/",
                    help="フォルダのベースURLを入力してください"
                )
                
                file_list_input = st.text_area(
                    "ファイルリスト（改行区切り）",
                    placeholder="""tokyo_area1.zip
tokyo_area2.zip
osaka_central.zip
kyoto_historical.zip""",
                    help="フォルダ内のファイル名を改行区切りで入力してください",
                    height=150
                )
                
                col1, col2 = st.columns(2)
                with col1:
                    prefix = st.text_input("プリセット名プレフィックス", value="📁", help="例: 📁, 🏢, 🌍")
                with col2:
                    auto_description = st.checkbox("自動説明生成", value=True, help="ファイル名から説明を自動生成")
                
                if st.form_submit_button("📁 フォルダ一括追加"):
                    if base_url and file_list_input:
                        # ベースURLの末尾にスラッシュを追加
                        if not base_url.endswith('/'):
                            base_url += '/'
                        
                        file_list = [f.strip() for f in file_list_input.split('\n') if f.strip()]
                        
                        if 'custom_presets' not in st.session_state:
                            st.session_state.custom_presets = {}
                        
                        added_count = 0
                        for filename in file_list:
                            # ファイル名からプリセット名を生成
                            preset_name = filename.replace('.zip', '').replace('.shp', '').replace('_', ' ').title()
                            full_preset_name = f"{prefix} {preset_name}"
                            
                            # 説明の生成
                            if auto_description:
                                description = f"{preset_name}の地理データ（{filename}）"
                            else:
                                description = f"フォルダから追加: {filename}"
                            
                            # プリセットに追加
                            st.session_state.custom_presets[full_preset_name] = {
                                "url": base_url + filename,
                                "description": description
                            }
                            added_count += 1
                        
                        st.success(f"✅ {added_count}個のプリセットを追加しました")
                        st.rerun()
                    else:
                        st.error("ベースURLとファイルリストは必須です")
        
        elif add_method == "🌐 URL一括追加":
            with st.form("batch_url_form"):
                st.markdown("**URL一括追加**")
                url_list_input = st.text_area(
                    "URLリスト（改行区切り）",
                    placeholder="""https://example.com/data1.zip
https://github.com/user/repo/blob/main/data2.zip
https://raw.githubusercontent.com/user/repo/main/data3.zip""",
                    help="複数のURLを改行区切りで入力してください",
                    height=150
                )
                
                col1, col2 = st.columns(2)
                with col1:
                    url_prefix = st.text_input("プリセット名プレフィックス", value="🌐", help="例: 🌐, 📊, 🗂️")
                with col2:
                    extract_name_method = st.selectbox(
                        "名前抽出方法",
                        ["ファイル名から", "URLの最後の部分", "手動入力"],
                        help="プリセット名の生成方法を選択"
                    )
                
                if extract_name_method == "手動入力":
                    name_list_input = st.text_area(
                        "プリセット名リスト（改行区切り）",
                        placeholder="""東京データセット1
大阪中央エリア
京都歴史地区""",
                        help="URLと同じ順序でプリセット名を入力してください"
                    )
                
                if st.form_submit_button("🌐 URL一括追加"):
                    if url_list_input:
                        url_list = [url.strip() for url in url_list_input.split('\n') if url.strip()]
                        
                        if extract_name_method == "手動入力":
                            if 'name_list_input' in locals() and name_list_input:
                                name_list = [name.strip() for name in name_list_input.split('\n') if name.strip()]
                                if len(name_list) != len(url_list):
                                    st.error("URLの数とプリセット名の数が一致しません")
                                    st.stop()
                            else:
                                st.error("手動入力を選択した場合はプリセット名リストが必要です")
                                st.stop()
                        
                        if 'custom_presets' not in st.session_state:
                            st.session_state.custom_presets = {}
                        
                        added_count = 0
                        for i, url in enumerate(url_list):
                            # プリセット名の生成
                            if extract_name_method == "ファイル名から":
                                filename = url.split('/')[-1]
                                preset_name = filename.replace('.zip', '').replace('.shp', '').replace('_', ' ').replace('-', ' ').title()
                            elif extract_name_method == "URLの最後の部分":
                                preset_name = url.split('/')[-2] if url.endswith('/') else url.split('/')[-1]
                                preset_name = preset_name.replace('_', ' ').replace('-', ' ').title()
                            else:  # 手動入力
                                preset_name = name_list[i]
                            
                            full_preset_name = f"{url_prefix} {preset_name}"
                            
                            # プリセットに追加
                            st.session_state.custom_presets[full_preset_name] = {
                                "url": url,
                                "description": f"URL一括追加: {preset_name}"
                            }
                            added_count += 1
                        
                        st.success(f"✅ {added_count}個のプリセットを追加しました")
                        st.rerun()
                    else:
                        st.error("URLリストは必須です")
        
        # カスタムプリセット表示
        if 'custom_presets' in st.session_state and st.session_state.custom_presets:
            st.markdown("**マイプリセット**")
            
            for preset_name, preset_info in st.session_state.custom_presets.items():
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    if st.button(f"📂 {preset_name}", key=f"custom_{preset_name}"):
                        try:
                            with st.spinner(f"{preset_name}を読み込み中..."):
                                st.session_state.gdf = extractor.load_shapefile_from_url(preset_info['url'])
                            
                            st.success(f"✅ {preset_name}を読み込み完了!")
                            st.info(f"📊 レコード数: {len(st.session_state.gdf):,}件")
                            
                            if st.session_state.gdf.crs:
                                st.info(f"🗺️ 座標系: {st.session_state.gdf.crs}")
                                
                            st.session_state.current_preset = preset_name
                                
                        except Exception as e:
                            st.error(f"❌ {str(e)}")
                
                with col2:
                    if st.button("🗑️", key=f"delete_{preset_name}", help="削除"):
                        del st.session_state.custom_presets[preset_name]
                        st.rerun()
        
        # プリセット管理機能
        st.markdown("---")
        st.markdown("**プリセット管理**")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("📤 プリセットエクスポート", help="現在のプリセットをJSONで出力"):
                if 'custom_presets' in st.session_state and st.session_state.custom_presets:
                    import json
                    preset_json = json.dumps(st.session_state.custom_presets, indent=2, ensure_ascii=False)
                    st.download_button(
                        "📁 presets.json",
                        data=preset_json,
                        file_name="my_presets.json",
                        mime="application/json"
                    )
                else:
                    st.info("カスタムプリセットがありません")
        
        with col2:
            uploaded_presets = st.file_uploader(
                "📥 プリセットインポート",
                type=['json'],
                help="以前エクスポートしたpresets.jsonを読み込み"
            )
            
            if uploaded_presets is not None:
                try:
                    import json
                    imported_presets = json.load(uploaded_presets)
                    
                    if 'custom_presets' not in st.session_state:
                        st.session_state.custom_presets = {}
                    
                    st.session_state.custom_presets.update(imported_presets)
                    st.success(f"✅ {len(imported_presets)}個のプリセットをインポートしました")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ インポートエラー: {str(e)}")
        
        with col3:
            if st.button("🗑️ 全プリセット削除", help="すべてのカスタムプリセットを削除"):
                if 'custom_presets' in st.session_state:
                    count = len(st.session_state.custom_presets)
                    st.session_state.custom_presets = {}
                    st.success(f"✅ {count}個のプリセットを削除しました")
                    st.rerun()
                else:
                    st.info("削除するプリセットがありません")
        
        # プリセットテンプレート機能
        st.markdown("---")
        st.markdown("**📋 プリセットテンプレート**")
        
        template_option = st.selectbox(
            "テンプレートを選択",
            [
                "選択してください...",
                "🏙️ 都市部データセット",
                "🌾 農村部データセット", 
                "🏢 企業・組織向け",
                "🎓 教育・研究機関向け",
                "🏛️ 行政機関向け"
            ]
        )
        
        if template_option != "選択してください...":
            if st.button(f"📋 {template_option}テンプレートを適用"):
                templates = {
                    "🏙️ 都市部データセット": {
                        "🏙️ 東京23区": {"url": "https://example.com/tokyo23.zip", "description": "東京23区の詳細公図データ"},
                        "🏙️ 大阪市中央": {"url": "https://example.com/osaka_central.zip", "description": "大阪市中央区の公図データ"},
                        "🏙️ 名古屋中区": {"url": "https://example.com/nagoya_naka.zip", "description": "名古屋市中区の公図データ"},
                        "🏙️ 横浜みなとみらい": {"url": "https://example.com/yokohama_mm.zip", "description": "横浜みなとみらい地区"}
                    },
                    "🌾 農村部データセット": {
                        "🌾 北海道十勝": {"url": "https://example.com/hokkaido_tokachi.zip", "description": "北海道十勝地方の農地データ"},
                        "🌾 新潟平野": {"url": "https://example.com/niigata_plain.zip", "description": "新潟平野の水田地帯"},
                        "🌾 熊本県阿蘇": {"url": "https://example.com/kumamoto_aso.zip", "description": "熊本県阿蘇地域の農地"},
                        "🌾 長野県佐久": {"url": "https://example.com/nagano_saku.zip", "description": "長野県佐久地方の高原農業地帯"}
                    },
                    "🏢 企業・組織向け": {
                        "🏢 本社周辺": {"url": "https://company-server.com/hq_area.zip", "description": "本社周辺の詳細データ"},
                        "🏭 工場エリアA": {"url": "https://company-server.com/factory_a.zip", "description": "A工場の敷地境界データ"},
                        "🏭 工場エリアB": {"url": "https://company-server.com/factory_b.zip", "description": "B工場の敷地境界データ"},
                        "📊 月次更新データ": {"url": "https://company-server.com/monthly_latest.zip", "description": "毎月更新される最新データ"}
                    },
                    "🎓 教育・研究機関向け": {
                        "🎓 キャンパス全体": {"url": "https://univ-server.edu/campus_all.zip", "description": "大学キャンパス全体の地図データ"},
                        "🔬 研究施設エリア": {"url": "https://univ-server.edu/research_area.zip", "description": "研究施設周辺のデータ"},
                        "📚 図書館周辺": {"url": "https://univ-server.edu/library_area.zip", "description": "図書館周辺の詳細地図"},
                        "🏟️ 体育施設": {"url": "https://univ-server.edu/sports_area.zip", "description": "体育施設エリアのデータ"}
                    },
                    "🏛️ 行政機関向け": {
                        "🏛️ 庁舎周辺": {"url": "https://city-server.go.jp/city_hall.zip", "description": "市庁舎周辺の公図データ"},
                        "🏥 公共施設": {"url": "https://city-server.go.jp/public_facilities.zip", "description": "公共施設の位置データ"},
                        "🚌 交通インフラ": {"url": "https://city-server.go.jp/transport.zip", "description": "交通インフラ関連データ"},
                        "🌳 公園緑地": {"url": "https://city-server.go.jp/parks.zip", "description": "公園・緑地のデータ"}
                    }
                }
                
                if 'custom_presets' not in st.session_state:
                    st.session_state.custom_presets = {}
                
                template_presets = templates[template_option]
                st.session_state.custom_presets.update(template_presets)
                
                st.success(f"✅ {template_option}テンプレート（{len(template_presets)}個）を適用しました")
                st.rerun()
    
    # メインエリア
    if st.session_state.gdf is not None:
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.header("🔍 検索条件")
            
            # 大字名選択（データが存在する場合のみ）
            try:
                if '大字名' in st.session_state.gdf.columns:
                    # NULL値を除外してソート
                    oaza_series = st.session_state.gdf['大字名'].dropna()
                    if len(oaza_series) > 0:
                        oaza_list = sorted(oaza_series.unique())
                        selected_oaza = st.selectbox("大字名を選択", oaza_list)
                    else:
                        st.error("❌ 大字名データがすべてNULLです")
                        selected_oaza = None
                else:
                    st.error("❌ '大字名'列が見つかりません。データの形式を確認してください。")
                    st.write("**利用可能な列:**", list(st.session_state.gdf.columns))
                    selected_oaza = None
            except Exception as e:
                st.error(f"❌ データ読み込みエラー: {str(e)}")
                st.write("**デバッグ情報:**")
                try:
                    oaza_info = st.session_state.gdf['大字名'].describe()
                    st.write("大字名列の統計:", oaza_info)
                    st.write("NULL値の数:", st.session_state.gdf['大字名'].isnull().sum())
                    st.write("ユニーク値の数:", st.session_state.gdf['大字名'].nunique())
                    st.write("データ型:", st.session_state.gdf['大字名'].dtype)
                except:
                    st.write("詳細情報の取得に失敗しました")
                selected_oaza = None
            
            # 地番入力
            chiban = st.text_input("地番を入力", value="1174")
            
            # 検索範囲
            range_m = st.number_input("検索範囲 (m)", min_value=1, max_value=1000, value=61)
            
            # 抽出ボタン
            if st.button("🚀 データ抽出", type="primary", use_container_width=True):
                if selected_oaza and chiban:
                    # 必要な列が存在するかチェック
                    required_columns = ['大字名', '地番']
                    missing_columns = [col for col in required_columns if col not in st.session_state.gdf.columns]
                    
                    if missing_columns:
                        st.error(f"❌ 必要な列が見つかりません: {missing_columns}")
                        st.write("**利用可能な列:**", list(st.session_state.gdf.columns))
                    else:
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
                elif not selected_oaza:
                    st.error("大字名を選択してください")
                else:
                    st.error("地番を入力してください")
        
        with col2:
            st.header("📊 データ一覧")
            
            # 現在のデータソース情報
            if 'data_source' in st.session_state:
                with st.expander("ℹ️ 現在のデータ情報"):
                    st.write(f"**データソース**: {st.session_state.data_source}")
                    if 'current_preset' in st.session_state:
                        st.write(f"**プリセット**: {st.session_state.current_preset}")
                    if 'file_info' in st.session_state:
                        st.write(f"**ファイル**: {st.session_state.file_info}")
                    
                    if st.session_state.gdf is not None:
                        st.write(f"**レコード数**: {len(st.session_state.gdf):,}件")
                        st.write(f"**カラム数**: {len(st.session_state.gdf.columns)}個")
                        if st.session_state.gdf.crs:
                            st.write(f"**座標系**: {st.session_state.gdf.crs}")
            
            # 大字名のサマリー
            if st.checkbox("大字名一覧を表示"):
                try:
                    if '大字名' in st.session_state.gdf.columns:
                        # NULL値を除外して集計
                        oaza_clean = st.session_state.gdf['大字名'].dropna()
                        if len(oaza_clean) > 0:
                            oaza_summary = oaza_clean.value_counts()
                            st.dataframe(oaza_summary.head(20), use_container_width=True)
                            
                            # NULL値の情報も表示
                            null_count = st.session_state.gdf['大字名'].isnull().sum()
                            if null_count > 0:
                                st.warning(f"⚠️ NULL値が{null_count}件あります")
                        else:
                            st.error("大字名データがすべてNULLまたは空です")
                    else:
                        st.warning("'大字名'列が見つかりません")
                except Exception as e:
                    st.error(f"データ表示エラー: {str(e)}")
            
            # 地番検索
            if st.checkbox("地番検索"):
                search_term = st.text_input("地番を検索", placeholder="例: 1174")
                if search_term:
                    try:
                        if '地番' in st.session_state.gdf.columns:
                            # 地番をstring型に変換してから検索（NULL値も考慮）
                            chiban_str = st.session_state.gdf['地番'].astype(str)
                            # 'nan'文字列も除外
                            filtered = st.session_state.gdf[
                                (chiban_str.str.contains(search_term, na=False)) & 
                                (chiban_str != 'nan') & 
                                (st.session_state.gdf['地番'].notna())
                            ]
                            
                            # 表示用の列を選択
                            display_columns = []
                            for col in ['大字名', '丁目名', '地番']:
                                if col in filtered.columns:
                                    display_columns.append(col)
                            
                            if display_columns and len(filtered) > 0:
                                st.dataframe(
                                    filtered[display_columns].head(20),
                                    use_container_width=True
                                )
                            elif len(filtered) == 0:
                                st.info(f"'{search_term}'に一致する地番が見つかりませんでした")
                            else:
                                st.warning("表示可能な列が見つかりません")
                        else:
                            st.warning("'地番'列が見つかりません")
                    except Exception as e:
                        st.error(f"検索エラー: {str(e)}")
                        # デバッグ情報
                        st.write("地番列のデータ型:", st.session_state.gdf['地番'].dtype)
                        st.write("地番列のNULL数:", st.session_state.gdf['地番'].isnull().sum())
            
            # データ構造の確認
            if st.checkbox("📋 データ構造を確認"):
                try:
                    st.write("**カラム一覧:**")
                    col_info = pd.DataFrame({
                        'カラム名': st.session_state.gdf.columns,
                        'データ型': st.session_state.gdf.dtypes.astype(str),
                        '非NULL数': st.session_state.gdf.count()
                    })
                    st.dataframe(col_info, use_container_width=True)
                    
                    st.write("**データサンプル (最初の5行):**")
                    display_df = st.session_state.gdf.head()
                    if 'geometry' in display_df.columns:
                        display_df = display_df.drop(columns=['geometry'])
                    st.dataframe(display_df, use_container_width=True)
                    
                except Exception as e:
                    st.error(f"データ構造確認エラー: {str(e)}")
        
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
        st.info("👆 データソースを選択してファイルを読み込んでください")
        
        # 使い方説明
        with st.expander("📖 使い方"):
            st.markdown("""
            ### 📋 データソース
            **1. ローカルファイル** 📁
            - SHPファイル一式をZIP圧縮してアップロード
            
            **2. Web URL** 🌐
            - 直接アクセス可能なファイルのURL
            - 例: `https://example.com/data.zip`
            
            **3. GitHub** 🐙
            - GitHubリポジトリ内のファイル
            - ユーザー名、リポジトリ名、ファイルパスを指定
            
            ### 📋 手順
            1. **データソース**を選択してファイルを読み込み
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
            
            ### 🔗 URL形式の例
            - **直接URL**: `https://example.com/shapefile.zip`
            - **GitHub**: `https://github.com/username/repo/blob/main/data.zip`
            - **GitHub Raw**: `https://raw.githubusercontent.com/username/repo/main/data.zip`
            """)

if __name__ == "__main__":
    main()