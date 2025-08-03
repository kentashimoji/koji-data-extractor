# -*- coding: utf-8 -*-
"""
電子公図データ抽出Webアプリ (Streamlit版) - Web/GitHub参照対応 - 丁目・小字選択機能付き
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
    
    def extract_data(self, gdf, oaza, chome, koaza, chiban, range_m):
        """データ抽出処理（丁目・小字対応）"""
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
            
            # 検索条件を構築（丁目・小字の有無に応じて）
            search_condition = (
                (gdf['大字名'] == oaza) & 
                (gdf['地番'] == chiban) &
                (gdf['大字名'].notna()) &
                (gdf['地番'].notna())
            )
            
            # 丁目が指定されている場合は条件に追加
            if chome is not None and chome != "選択なし" and '丁目名' in gdf.columns:
                search_condition = search_condition & (gdf['丁目名'] == chome) & (gdf['丁目名'].notna())
            
            # 小字が指定されている場合は条件に追加
            if koaza is not None and koaza != "選択なし" and '小字名' in gdf.columns:
                search_condition = search_condition & (gdf['小字名'] == koaza) & (gdf['小字名'].notna())
            
            df = gdf[search_condition]
            
            if df.empty:
                # デバッグ情報を提供
                debug_info = []
                oaza_matches = gdf[gdf['大字名'] == oaza]['大字名'].count()
                chiban_matches = gdf[gdf['地番'] == chiban]['地番'].count()
                
                debug_info.append(f"大字名'{oaza}'の該当件数: {oaza_matches}")
                debug_info.append(f"地番'{chiban}'の該当件数: {chiban_matches}")
                
                if chome and chome != "選択なし" and '丁目名' in gdf.columns:
                    chome_matches = gdf[gdf['丁目名'] == chome]['丁目名'].count()
                    debug_info.append(f"丁目名'{chome}'の該当件数: {chome_matches}")
                
                if koaza and koaza != "選択なし" and '小字名' in gdf.columns:
                    koaza_matches = gdf[gdf['小字名'] == koaza]['小字名'].count()
                    debug_info.append(f"小字名'{koaza}'の該当件数: {koaza_matches}")
                
                return None, None, f"該当する筆が見つかりませんでした。{' / '.join(debug_info)}"
            
            # 利用可能な列のみを選択
            available_columns = ["大字名", "地番", "geometry"]
            if "丁目名" in gdf.columns:
                available_columns.insert(1, "丁目名")
            if "小字名" in gdf.columns:
                insert_position = 2 if "丁目名" in available_columns else 1
                available_columns.insert(insert_position, "小字名")
            
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
            
            # 周辺筆抽出用のデータフレーム作成（利用可能な列のみ使用）
            overlay_columns = ['地番', 'geometry']
            if '大字名' in valid_data.columns:
                overlay_columns.insert(0, '大字名')
            if '丁目名' in valid_data.columns:
                overlay_columns.insert(-1, '丁目名')
            if '小字名' in valid_data.columns:
                overlay_columns.insert(-1, '小字名')
            
            existing_overlay_columns = [col for col in overlay_columns if col in valid_data.columns]
            df2 = gpd.GeoDataFrame(valid_data[existing_overlay_columns])
            
            overlay_gdf = df1.overlay(df2, how='intersection')
            
            return df_summary, overlay_gdf, f"対象筆: {len(df_summary)}件, 周辺筆: {len(overlay_gdf)}件"
            
        except Exception as e:
            return None, None, f"エラー: {str(e)}"

def get_chome_options(gdf, selected_oaza):
    """指定された大字名に対応する丁目の選択肢を取得"""
    try:
        if '丁目名' not in gdf.columns:
            return None
        
        # 指定された大字名でフィルタリング
        filtered_gdf = gdf[
            (gdf['大字名'] == selected_oaza) & 
            (gdf['大字名'].notna()) &
            (gdf['丁目名'].notna())
        ]
        
        if len(filtered_gdf) == 0:
            return None
        
        # 丁目名のユニークな値を取得してソート
        chome_list = sorted(filtered_gdf['丁目名'].unique())
        
        return chome_list
        
    except Exception as e:
        st.error(f"丁目名取得エラー: {str(e)}")
        return None

def get_koaza_options(gdf, selected_oaza, selected_chome=None):
    """指定された大字名（及び丁目名）に対応する小字の選択肢を取得"""
    try:
        if '小字名' not in gdf.columns:
            return None
        
        # フィルタ条件を構築
        filter_condition = (
            (gdf['大字名'] == selected_oaza) & 
            (gdf['大字名'].notna()) &
            (gdf['小字名'].notna())
        )
        
        # 丁目が指定されている場合は条件に追加
        if selected_chome and selected_chome != "選択なし" and '丁目名' in gdf.columns:
            filter_condition = filter_condition & (gdf['丁目名'] == selected_chome) & (gdf['丁目名'].notna())
        
        # 指定された条件でフィルタリング
        filtered_gdf = gdf[filter_condition]
        
        if len(filtered_gdf) == 0:
            return None
        
        # 小字名のユニークな値を取得してソート
        koaza_list = sorted(filtered_gdf['小字名'].unique())
        
        return koaza_list
        
    except Exception as e:
        st.error(f"小字名取得エラー: {str(e)}")
        return None

def main():
    st.title("🗺️ 電子公図データ抽出ツール")
    st.markdown("---")
    
    extractor = KojiWebExtractor()
    
    # サイドバー
    st.sidebar.header("📋 プリセットファイル")
    
    # プリセットファイル機能
    preset_files = {
        "サンプル1": {
            "name": "東京都サンプル地番データ",
            "url": "https://example.com/tokyo_sample.zip",
            "description": "東京都の地番データサンプル（丁目・小字対応）"
        },
        "サンプル2": {
            "name": "大阪府サンプル地番データ", 
            "url": "https://example.com/osaka_sample.zip",
            "description": "大阪府の地番データサンプル（小字対応）"
        },
        "サンプル3": {
            "name": "基本地番データ",
            "url": "https://example.com/basic_sample.zip", 
            "description": "基本的な地番データ（大字名・地番のみ）"
        }
    }
    
    # プリセット選択
    selected_preset = st.sidebar.selectbox(
        "プリセットファイルを選択",
        ["選択なし"] + list(preset_files.keys()),
        help="事前に設定されたサンプルファイルから選択できます"
    )
    
    if selected_preset != "選択なし":
        preset_info = preset_files[selected_preset]
        st.sidebar.info(f"**{preset_info['name']}**\n\n{preset_info['description']}")
        
        if st.sidebar.button("📋 プリセットファイルを読み込み", type="secondary"):
            try:
                with st.spinner(f"プリセット「{selected_preset}」を読み込み中..."):
                    st.session_state.gdf = extractor.load_shapefile_from_url(preset_info['url'])
                
                st.sidebar.success("✅ プリセット読み込み完了!")
                st.sidebar.info(f"📊 レコード数: {len(st.session_state.gdf):,}件")
                
                if st.session_state.gdf.crs:
                    st.sidebar.info(f"🗺️ 座標系: {st.session_state.gdf.crs}")
                
                # 丁目名・小字名列の存在確認
                if '丁目名' in st.session_state.gdf.columns:
                    chome_count = st.session_state.gdf['丁目名'].notna().sum()
                    st.sidebar.info(f"🏘️ 丁目データ: {chome_count}件")
                
                if '小字名' in st.session_state.gdf.columns:
                    koaza_count = st.session_state.gdf['小字名'].notna().sum()
                    st.sidebar.info(f"🏞️ 小字データ: {koaza_count}件")
                
                # データソース情報を記録
                st.session_state.data_source = "プリセット"
                st.session_state.current_preset = selected_preset
                st.session_state.file_info = preset_info['name']
                    
            except Exception as e:
                st.sidebar.error(f"❌ プリセット読み込みエラー: {str(e)}")
    
    st.sidebar.markdown("---")
    st.sidebar.header("📂 データソース選択")
    
    # データソース選択
    data_source = st.sidebar.radio(
        "独自データソースを選択",
        ["📁 ローカルファイル", "🌐 Web URL", "🐙 GitHub"],
        help="独自のデータファイルを使用する場合の取得方法を選択してください"
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
                        
                        # 丁目名・小字名列の存在確認
                        if '丁目名' in st.session_state.gdf.columns:
                            chome_count = st.session_state.gdf['丁目名'].notna().sum()
                            st.sidebar.info(f"🏘️ 丁目データ: {chome_count}件")
                        
                        if '小字名' in st.session_state.gdf.columns:
                            koaza_count = st.session_state.gdf['小字名'].notna().sum()
                            st.sidebar.info(f"🏞️ 小字データ: {koaza_count}件")
                        
                        # データソース情報を記録
                        st.session_state.data_source = "ローカルファイル"
                        st.session_state.file_info = uploaded_file.name
                        if 'current_preset' in st.session_state:
                            del st.session_state.current_preset
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
                    
                    # 丁目名・小字名列の存在確認
                    if '丁目名' in st.session_state.gdf.columns:
                        chome_count = st.session_state.gdf['丁目名'].notna().sum()
                        st.sidebar.info(f"🏘️ 丁目データ: {chome_count}件")
                    
                    if '小字名' in st.session_state.gdf.columns:
                        koaza_count = st.session_state.gdf['小字名'].notna().sum()
                        st.sidebar.info(f"🏞️ 小字データ: {koaza_count}件")
                    
                    # データソース情報を記録
                    st.session_state.data_source = "Web URL"
                    st.session_state.file_info = web_url
                    if 'current_preset' in st.session_state:
                        del st.session_state.current_preset
                        
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
                    
                    # 丁目名・小字名列の存在確認
                    if '丁目名' in st.session_state.gdf.columns:
                        chome_count = st.session_state.gdf['丁目名'].notna().sum()
                        st.sidebar.info(f"🏘️ 丁目データ: {chome_count}件")
                    
                    if '小字名' in st.session_state.gdf.columns:
                        koaza_count = st.session_state.gdf['小字名'].notna().sum()
                        st.sidebar.info(f"🏞️ 小字データ: {koaza_count}件")
                    
                    # データソース情報を記録
                    st.session_state.data_source = "GitHub"
                    st.session_state.file_info = github_url
                    if 'current_preset' in st.session_state:
                        del st.session_state.current_preset
                        
                except Exception as e:
                    st.sidebar.error(f"❌ {str(e)}")
            else:
                st.sidebar.error("GitHubの情報をすべて入力してください")
    
    # メインエリア
    if st.session_state.gdf is not None:
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.header("🔍 検索条件")
            
            # 大字名選択（データが存在する場合のみ）
            selected_oaza = None
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
                selected_oaza = None
            
            # 丁目名選択（大字名が選択されている場合のみ）
            selected_chome = None
            if selected_oaza is not None:
                chome_options = get_chome_options(st.session_state.gdf, selected_oaza)
                
                if chome_options is not None and len(chome_options) > 0:
                    # 丁目選択肢がある場合
                    chome_list_with_none = ["選択なし"] + chome_options
                    selected_chome = st.selectbox(
                        "丁目名を選択（任意）", 
                        chome_list_with_none,
                        help="丁目を指定する場合は選択してください。指定しない場合は「選択なし」のままにしてください。"
                    )
                    
                    if selected_chome == "選択なし":
                        st.info("💡 丁目を指定せずに検索します")
                    else:
                        st.success(f"✅ 丁目「{selected_chome}」を指定しました")
                        
                elif '丁目名' in st.session_state.gdf.columns:
                    # 丁目名列は存在するが、この大字名には丁目データがない
                    st.info("ℹ️ この大字名には丁目データがありません")
                else:
                    # 丁目名列自体が存在しない
                    st.info("ℹ️ このデータセットには丁目情報が含まれていません")
            
            # 小字名選択（大字名が選択されている場合のみ）
            selected_koaza = None
            if selected_oaza is not None:
                koaza_options = get_koaza_options(st.session_state.gdf, selected_oaza, selected_chome)
                
                if koaza_options is not None and len(koaza_options) > 0:
                    # 小字選択肢がある場合
                    koaza_list_with_none = ["選択なし"] + koaza_options
                    selected_koaza = st.selectbox(
                        "小字名を選択（任意）", 
                        koaza_list_with_none,
                        help="小字を指定する場合は選択してください。指定しない場合は「選択なし」のままにしてください。"
                    )
                    
                    if selected_koaza == "選択なし":
                        st.info("💡 小字を指定せずに検索します")
                    else:
                        st.success(f"✅ 小字「{selected_koaza}」を指定しました")
                        
                elif '小字名' in st.session_state.gdf.columns:
                    # 小字名列は存在するが、この大字名（丁目名）には小字データがない
                    condition_text = f"大字名「{selected_oaza}」"
                    if selected_chome and selected_chome != "選択なし":
                        condition_text += f"・丁目名「{selected_chome}」"
                    st.info(f"ℹ️ {condition_text}には小字データがありません")
                else:
                    # 小字名列自体が存在しない
                    st.info("ℹ️ このデータセットには小字情報が含まれていません")
            
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
                                st.session_state.gdf, selected_oaza, selected_chome, selected_koaza, chiban, range_m
                            )
                        
                        st.info(message)
                        
                        if target_gdf is not None and overlay_gdf is not None:
                            # 結果を保存
                            st.session_state.target_gdf = target_gdf
                            st.session_state.overlay_gdf = overlay_gdf
                            
                            # ファイル名の生成（丁目・小字が指定されている場合は含める）
                            file_name_parts = [selected_oaza]
                            if selected_chome and selected_chome != "選択なし":
                                file_name_parts.append(selected_chome)
                            if selected_koaza and selected_koaza != "選択なし":
                                file_name_parts.append(selected_koaza)
                            file_name_parts.append(chiban)
                            
                            st.session_state.file_name = "_".join(file_name_parts)
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
                        
                        # 丁目・小字データの有無を表示
                        if '丁目名' in st.session_state.gdf.columns:
                            chome_count = st.session_state.gdf['丁目名'].notna().sum()
                            total_count = len(st.session_state.gdf)
                            st.write(f"**丁目データ**: {chome_count}/{total_count}件 ({chome_count/total_count*100:.1f}%)")
                        
                        if '小字名' in st.session_state.gdf.columns:
                            koaza_count = st.session_state.gdf['小字名'].notna().sum()
                            total_count = len(st.session_state.gdf)
                            st.write(f"**小字データ**: {koaza_count}/{total_count}件 ({koaza_count/total_count*100:.1f}%)")
            
            # 大字名・丁目名・小字名のサマリー
            if st.checkbox("大字名・丁目名・小字名一覧を表示"):
                try:
                    if '大字名' in st.session_state.gdf.columns:
                        # NULL値を除外して集計
                        oaza_clean = st.session_state.gdf['大字名'].dropna()
                        if len(oaza_clean) > 0:
                            st.write("**大字名別集計:**")
                            oaza_summary = oaza_clean.value_counts()
                            st.dataframe(oaza_summary.head(20), use_container_width=True)
                            
                            # 丁目名の集計も表示
                            if '丁目名' in st.session_state.gdf.columns:
                                chome_clean = st.session_state.gdf['丁目名'].dropna()
                                if len(chome_clean) > 0:
                                    st.write("**丁目名別集計:**")
                                    chome_summary = chome_clean.value_counts()
                                    st.dataframe(chome_summary.head(20), use_container_width=True)
                            
                            # 小字名の集計も表示
                            if '小字名' in st.session_state.gdf.columns:
                                koaza_clean = st.session_state.gdf['小字名'].dropna()
                                if len(koaza_clean) > 0:
                                    st.write("**小字名別集計:**")
                                    koaza_summary = koaza_clean.value_counts()
                                    st.dataframe(koaza_summary.head(20), use_container_width=True)
                            
                            # 大字名×丁目名×小字名のクロス集計
                            cross_columns = ['大字名']
                            if '丁目名' in st.session_state.gdf.columns:
                                cross_columns.append('丁目名')
                            if '小字名' in st.session_state.gdf.columns:
                                cross_columns.append('小字名')
                            
                            if len(cross_columns) > 1:
                                st.write(f"**{' × '.join(cross_columns)}の組み合わせ:**")
                                cross_data = st.session_state.gdf.copy()
                                
                                # 各列がNULLでないデータのみ抽出
                                for col in cross_columns:
                                    cross_data = cross_data[cross_data[col].notna()]
                                
                                if len(cross_data) > 0:
                                    cross_summary = cross_data.groupby(cross_columns).size().reset_index(name='件数')
                                    cross_summary = cross_summary.sort_values('件数', ascending=False)
                                    st.dataframe(cross_summary.head(20), use_container_width=True)
                            
                            # NULL値の情報も表示
                            null_info = []
                            for col in ['大字名', '丁目名', '小字名']:
                                if col in st.session_state.gdf.columns:
                                    null_count = st.session_state.gdf[col].isnull().sum()
                                    if null_count > 0:
                                        null_info.append(f"{col}: {null_count}件")
                            
                            if null_info:
                                st.warning(f"⚠️ NULL値: {', '.join(null_info)}")
                        else:
                            st.error("大字名データがすべてNULLまたは空です")
                    else:
                        st.warning("'大字名'列が見つかりません")
                except Exception as e:
                    st.error(f"データ表示エラー: {str(e)}")
            
            # 地番検索（改良版）
            if st.checkbox("地番検索"):
                search_term = st.text_input("地番を検索", placeholder="例: 1174")
                
                # 検索オプション
                col_search1, col_search2 = st.columns(2)
                with col_search1:
                    exact_match = st.checkbox("完全一致", value=False, help="チェックすると完全一致で検索します")
                with col_search2:
                    show_geometry = st.checkbox("座標情報を表示", value=False, help="検索結果に座標情報を含めます")
                
                if search_term:
                    try:
                        if '地番' in st.session_state.gdf.columns:
                            # 地番をstring型に変換してから検索（NULL値も考慮）
                            chiban_str = st.session_state.gdf['地番'].astype(str)
                            
                            if exact_match:
                                # 完全一致検索
                                filtered = st.session_state.gdf[
                                    (chiban_str == search_term) & 
                                    (chiban_str != 'nan') & 
                                    (st.session_state.gdf['地番'].notna())
                                ]
                            else:
                                # 部分一致検索
                                filtered = st.session_state.gdf[
                                    (chiban_str.str.contains(search_term, na=False)) & 
                                    (chiban_str != 'nan') & 
                                    (st.session_state.gdf['地番'].notna())
                                ]
                            
                            # 表示用の列を選択
                            display_columns = []
                            for col in ['大字名', '丁目名', '小字名', '地番']:
                                if col in filtered.columns:
                                    display_columns.append(col)
                            
                            # 座標情報を追加する場合
                            if show_geometry and 'geometry' in filtered.columns:
                                filtered_with_coords = filtered.copy()
                                filtered_with_coords['中心X座標'] = filtered_with_coords['geometry'].centroid.x
                                filtered_with_coords['中心Y座標'] = filtered_with_coords['geometry'].centroid.y
                                display_columns.extend(['中心X座標', '中心Y座標'])
                                filtered = filtered_with_coords
                            
                            if display_columns and len(filtered) > 0:
                                st.write(f"**検索結果: {len(filtered)}件**")
                                st.dataframe(
                                    filtered[display_columns].head(50),
                                    use_container_width=True
                                )
                                
                                # 検索結果が多い場合の警告
                                if len(filtered) > 50:
                                    st.info(f"ℹ️ 結果が{len(filtered)}件あります。最初の50件のみ表示しています。")
                                    
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
                        '非NULL数': st.session_state.gdf.count(),
                        'NULL数': st.session_state.gdf.isnull().sum()
                    })
                    col_info['NULL率(%)'] = (col_info['NULL数'] / len(st.session_state.gdf) * 100).round(1)
                    st.dataframe(col_info, use_container_width=True)
                    
                    st.write("**データサンプル (最初の5行):**")
                    display_df = st.session_state.gdf.head()
                    if 'geometry' in display_df.columns:
                        display_df = display_df.drop(columns=['geometry'])
                    st.dataframe(display_df, use_container_width=True)
                    
                    # 統計情報の表示
                    st.write("**基本統計:**")
                    stats_info = {
                        '総レコード数': len(st.session_state.gdf),
                        '座標系': str(st.session_state.gdf.crs) if st.session_state.gdf.crs else '不明',
                        '大字名の種類数': st.session_state.gdf['大字名'].nunique() if '大字名' in st.session_state.gdf.columns else 'なし',
                        '地番の種類数': st.session_state.gdf['地番'].nunique() if '地番' in st.session_state.gdf.columns else 'なし'
                    }
                    
                    if '丁目名' in st.session_state.gdf.columns:
                        stats_info['丁目名の種類数'] = st.session_state.gdf['丁目名'].nunique()
                        stats_info['丁目データ有り'] = st.session_state.gdf['丁目名'].notna().sum()
                    
                    if '小字名' in st.session_state.gdf.columns:
                        stats_info['小字名の種類数'] = st.session_state.gdf['小字名'].nunique()
                        stats_info['小字データ有り'] = st.session_state.gdf['小字名'].notna().sum()
                    
                    for key, value in stats_info.items():
                        st.write(f"- **{key}**: {value}")
                    
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
            
            tab1, tab2, tab3 = st.tabs(["対象筆", "周辺筆", "検索条件"])
            
            with tab1:
                if not st.session_state.target_gdf.empty:
                    st.write("**対象筆の詳細情報:**")
                    display_df = st.session_state.target_gdf.drop(columns=['geometry'])
                    st.dataframe(display_df, use_container_width=True)
                    
                    # 対象筆の座標情報
                    if st.checkbox("対象筆の座標情報を表示"):
                        coords_df = st.session_state.target_gdf.copy()
                        coords_df['中心X座標'] = coords_df['geometry'].centroid.x
                        coords_df['中心Y座標'] = coords_df['geometry'].centroid.y
                        coords_df['面積(m²)'] = coords_df['geometry'].area
                        coord_display = coords_df[['中心X座標', '中心Y座標', '面積(m²)']]
                        st.dataframe(coord_display, use_container_width=True)
            
            with tab2:
                if not st.session_state.overlay_gdf.empty:
                    st.write(f"**周辺筆一覧 ({len(st.session_state.overlay_gdf)}件):**")
                    display_df = st.session_state.overlay_gdf.drop(columns=['geometry'])
                    st.dataframe(display_df, use_container_width=True)
                    
                    # 周辺筆の統計情報
                    if st.checkbox("周辺筆の統計情報を表示"):
                        st.write("**周辺筆の統計:**")
                        stats_cols = []
                        for col in ['大字名', '丁目名', '小字名', '地番']:
                            if col in st.session_state.overlay_gdf.columns:
                                stats_cols.append(col)
                        
                        if stats_cols:
                            for col in stats_cols:
                                if col in st.session_state.overlay_gdf.columns:
                                    unique_count = st.session_state.overlay_gdf[col].nunique()
                                    st.write(f"- **{col}の種類数**: {unique_count}")
                        
                        # 面積統計
                        area_stats = st.session_state.overlay_gdf['geometry'].area.describe()
                        st.write("**面積統計 (m²):**")
                        st.dataframe(area_stats.round(2), use_container_width=True)
            
            with tab3:
                st.write("**使用した検索条件:**")
                search_conditions = {
                    '大字名': selected_oaza if 'selected_oaza' in locals() else '不明',
                    '地番': chiban if 'chiban' in locals() else '不明',
                    '検索範囲': f"{range_m}m" if 'range_m' in locals() else '不明'
                }
                
                if 'selected_chome' in locals() and selected_chome and selected_chome != "選択なし":
                    search_conditions['丁目名'] = selected_chome
                else:
                    search_conditions['丁目名'] = '指定なし'
                
                if 'selected_koaza' in locals() and selected_koaza and selected_koaza != "選択なし":
                    search_conditions['小字名'] = selected_koaza
                else:
                    search_conditions['小字名'] = '指定なし'
                
                for key, value in search_conditions.items():
                    st.write(f"- **{key}**: {value}")
                
                # 抽出結果のサマリー
                st.write("**抽出結果サマリー:**")
                result_summary = {
                    '対象筆件数': len(st.session_state.target_gdf),
                    '周辺筆件数': len(st.session_state.overlay_gdf),
                    '総抽出件数': len(st.session_state.target_gdf) + len(st.session_state.overlay_gdf)
                }
                
                for key, value in result_summary.items():
                    st.write(f"- **{key}**: {value}件")
    
    else:
        st.info("👆 データソースを選択してファイルを読み込んでください")
        
        # 使い方説明（改良版）
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
            3. **丁目名**を選択（丁目データがある場合のみ表示）
               - 丁目を指定したくない場合は「選択なし」のまま
            4. **小字名**を選択（小字データがある場合のみ表示）
               - 小字を指定したくない場合は「選択なし」のまま
            5. **地番**を入力
            6. **検索範囲**を設定（デフォルト: 61m）
            7. **データ抽出**ボタンをクリック
            8. **KMLファイル**をダウンロード
            
            ### 🏘️ 丁目・小字機能について
            - データに「丁目名」「小字名」列が含まれている場合、それぞれでの絞り込みが可能
            - 大字名を選択すると、その大字に対応する丁目・小字のみが表示されます
            - 丁目を選択すると、その丁目に対応する小字のみが表示されます
            - 丁目・小字を指定しない場合は、上位の地域区分内の全ての筆が検索対象になります
            
            ### 🎯 出力ファイル
            - **対象筆KML**: 指定した筆のKMLファイル
            - **周辺筆KML**: 周辺筆のKMLファイル
            - **CSV**: 座標情報付きのCSVファイル
            
            ### 🗺️ 対応ソフトウェア
            - Google Earth
            - Google マイマップ
            - QGIS
            - その他GISソフトウェア
            
            ### 🔍 検索機能
            - **地番検索**: 完全一致・部分一致での地番検索
            - **座標表示**: 検索結果に中心座標を表示可能
            - **データ構造確認**: 列情報、NULL値統計、サンプルデータの確認
            - **階層検索**: 大字名→丁目名→小字名の階層での絞り込み検索
            
            ### 🔗 URL形式の例
            - **直接URL**: `https://example.com/shapefile.zip`
            - **GitHub**: `https://github.com/username/repo/blob/main/data.zip`
            - **GitHub Raw**: `https://raw.githubusercontent.com/username/repo/main/data.zip`
            
            ### 📍 地域区分の階層
            ```
            大字名 (必須)
            ├── 丁目名 (任意)
            │   └── 小字名 (任意)
            └── 小字名 (任意、丁目なしの場合)
            ```
            """)

if __name__ == "__main__":
    main()
