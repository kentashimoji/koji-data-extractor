    # 検索結果からファイル選択
    if 'matching_files' in st.session_state and st.session_state.matching_files:
        st.sidebar.write(f"**🎯 {st.session_state.selected_municipality}の対象ファイル:**")
        
        file_options = ["選択してください"] + [f["name"] for f in st.session_state.matching_files]
        selected_file = st.sidebar.selectbox(
            "ファイルを選択",
            file_options,
            help="読み込むShapefileを選択してください"
        )
        
        if selected_file != "選択してください":
            selected_file_info = next((f for f in st.session_state.matching_files if f["name"] == selected_file), None)
            
            if selected_file_info:
                st.sidebar.info(f"**{selected_file_info['name']}**\n\n{selected_file_info['description']}")
                
                if st.sidebar.button("📥 選択ファイルを読み込み", type="primary"):
                    try:
                        with st.spinner(f"ファイル「{selected_file}」を読み込み中..."):
                            st.session_state.gdf = extractor.load_shapefile_from_url(selected_file_info['url'])
                        
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
                        st.session_state.data_source = "Excel自治体選択"
                        st.session_state.current_file = selected_file
                        st.session_state.file_url = selected_file_info['url']
                            
                    except Exception as e:
                        st.sidebar.error(f"❌ ファイル読み込みエラー: {str(e)}")
    
    # メインエリア
    if st.session_state.gdf is not None:
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.header("🔍 検索条件")
            
            # 現在のデータ情報を表示
            if 'selected_municipality' in st.session_state:
                st.info(f"📍 現在のデータ: {st.session_state.selected_municipality}")
                if 'municipality_code' in st.session_state:
                    st.info(f"🏛️ 自治体コード: {st.session_state.municipality_code}")
            
            # 大字名選択
            selected_oaza = None
            try:
                if '大字名' in st.session_state.gdf.columns:
                    oaza_series = st.session_state.gdf['大字名'].dropna()
                    if len(oaza_series) > 0:
                        oaza_list = sorted(oaza_series.unique())
                        selected_oaza = st.selectbox("大字名を選択", oaza_list)
                    else:
                        st.error("❌ 大字名データがすべてNULLです")
                        selected_oaza = None
                else:
                    st.error("❌ '大字名'列が見つかりません。")
                    st.write("**利用可能な列:**", list(st.session_state.gdf.columns))
                    selected_oaza = None
            except Exception as e:
                st.error(f"❌ データ読み込みエラー: {str(e)}")
                selected_oaza = None
            
            # 丁目名選択
            selected_chome = None
            if selected_oaza is not None:
                chome_options = get_chome_options(st.session_state.gdf, selected_oaza)
                
                if chome_options is not None and len(chome_options) > 0:
                    chome_list_with_none = ["選択なし"] + chome_options
                    selected_chome = st.selectbox(
                        "丁目名を選択（任意）", 
                        chome_list_with_none,
                        help="丁目を指定する場合は選択してください"
                    )
                    
                    if selected_chome == "選択なし":
                        st.info("💡 丁目を指定せずに検索します")
                    else:
                        st.success(f"✅ 丁目「{selected_chome}」を指定しました")
                        
                elif '丁目名' in st.session_state.gdf.columns:
                    st.info("ℹ️ この大字名には丁目データがありません")
                else:
                    st.info("ℹ️ このデータセットには丁目情報が含まれていません")
            
            # 小字名選択
            selected_koaza = None
            if selected_oaza is not None:
                koaza_options = get_koaza_options(st.session_state.gdf, selected_oaza, selected_chome)
                
                if koaza_options is not None and len(koaza_options) > 0:
                    koaza_list_with_none = ["選択なし"] + koaza_options
                    selected_koaza = st.selectbox(
                        "小字名を選択（任意）", 
                        koaza_list_with_none,
                        help="小字を指定する場合は選択してください"
                    )
                    
                    if selected_koaza == "選択なし":
                        st.info("💡 小字を指定せずに検索します")
                    else:
                        st.success(f"✅ 小字「{selected_koaza}」を指定しました")
                        
                elif '小字名' in st.session_state.gdf.columns:
                    condition_text = f"大字名「{selected_oaza}」"
                    if selected_chome and selected_chome != "選択なし":
                        condition_text += f"・丁目名「{selected_chome}」"
                    st.info(f"ℹ️ {condition_text}には小字データがありません")
                else:
                    st.info("ℹ️ このデータセットには小字情報が含まれていません")
            
            # 地番入力
            chiban = st.text_input("地番を入力", value="1174")
            
            # 検索範囲
            range_m = 61
            
            # 抽出ボタン
            if st.button("🚀 データ抽出", type="primary", use_container_width=True):
                if selected_oaza and chiban:
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
            
            # 現在のデータ情報を表示
            if 'selected_municipality' in st.session_state:
                with st.expander("ℹ️ 現在のデータ情報"):
                    st.write(f"**データソース**: Excel自治体データ連携")
                    st.write(f"**選択自治体**: {st.session_state.selected_municipality}")
                    if 'municipality_code' in st.session_state:
                        st.write(f"**自治体コード**: {st.session_state.municipality_code}")
                    if 'current_file' in st.session_state:
                        st.write(f"**読み込みファイル**: {st.session_state.current_file}")
                    
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
            
            # 自治体データ情報の表示
            if st.session_state.municipal_data is not None:
                if st.checkbox("🏛️ 自治体データ情報を表示"):
                    st.write("**自治体データベース情報:**")
                    st.write(f"- **総自治体数**: {len(st.session_state.municipal_data)}件")
                    st.write(f"- **都道府県数**: {st.session_state.municipal_data['都道府県名（漢字）'].nunique()}件")
                    
                    # 都道府県別の自治体数
                    prefecture_counts = st.session_state.municipal_data['都道府県名（漢字）'].value_counts().head(10)
                    st.write("**都道府県別自治体数（上位10位）:**")
                    st.dataframe(prefecture_counts, use_container_width=True)
            
            # 検索結果ファイル一覧
            if 'matching_files' in st.session_state and st.session_state.matching_files:
                if st.checkbox("🗂️ 検索結果ファイル一覧を表示"):
                    st.write(f"**🎯 {st.session_state.selected_municipality}の対象ファイル一覧:**")
                    
                    files_df = pd.DataFrame(st.session_state.matching_files)
                    
                    # ファイル情報を整理して表示
                    display_df = pd.DataFrame({
                        'ファイル名': files_df['name'],
                        '説明': files_df['description'],
                        'サイズ': files_df['size'].apply(
                            lambda x: f"{x:,} bytes" if x is not None else "不明"
                        )
                    })
                    
                    st.dataframe(display_df, use_container_width=True)
            
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
            
            # 地番検索
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
                    '自治体': f"{st.session_state.selected_municipality}（{st.session_state.municipality_code}）" if 'selected_municipality' in st.session_state else '不明',
                    '大字名': selected_oaza if 'selected_oaza' in locals() else '不明',
                    '地番': chiban if 'chiban' in locals() else '不明',
                    '検索範囲': "61m（固定）"
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
        st.info("👆 自治体を選択してファイルを読み込んでください")
        
        # 使い方説明
        with st.expander("📖 使い方"):
            st.markdown("""
            ### 🏛️ Excel自治体データ連携機能
            **自動自治体コード変換システム** 📊
            - Excel自治体データ（000925835.xlsx）から自治体情報を自動読み込み
            - 都道府県 → 市区町村の階層選択
            - 自治体名から自治体コードへの自動変換
            - 自治体コードに基づく自動ファイル検索・抽出
            
            **使用手順:**
            1. **都道府県**をプルダウンから選択
            2. **自治体**をプルダウンから選択（自治体コードが自動表示）
            3. **データフォルダURL**を設定（デフォルト値使用可能）
            4. **「該当ファイルを検索」**ボタンをクリック
            5. 検索されたファイル一覧から**目的のファイルを選択**
            6. **「選択ファイルを読み込み」**ボタンでデータを読み込み
            
            ### 📋 検索・抽出手順
            1. **大字名**をドロップダウンから選択
            2. **丁目名**を選択（丁目データがある場合のみ表示）
               - 指定しない場合は「選択なし」のまま
            3. **小字名**を選択（小字データがある場合のみ表示）
               - 指定しない場合は「選択なし」のまま
            4. **地番**を入力（例: 1174）
            5. **データ抽出**ボタンをクリック
            6. **KMLファイル**をダウンロード
            
            ### 🎯 出力ファイル
            - **対象筆KML**: 指定した筆のKMLファイル
            - **周辺筆KML**: 周辺筆のKMLファイル（61m範囲内）
            - **CSV**: 座標情報付きのCSVファイル
            
            ### 🔍 検索・分析機能
            - **Excel連携自治体選択**: 公式データに基づく正確な自治体選択
            - **自動ファイル発見**: 自治体コードに基づくファイル自動検索
            - **階層地域選択**: 大字名→丁目名→小字名の階層選択
            - **地番検索**: 完全一致・部分一致での地番検索
            - **座標情報表示**: 検索結果に中心座標を表示可能
            - **統計情報**: 各地域区分の件数・割合の確認
            - **データ構造確認**: 列情報、NULL値統計、サンプルデータの確認
            
            ### 🗺️ 対応ソフトウェア
            - **Google Earth**: KMLファイル直接読み込み
            - **Google マイマップ**: KMLファイルインポート
            - **QGIS**: オープンソースGISソフトウェア
            - **ArcGIS**: 商用GISソフトウェア
            - **その他**: KML対応のGISソフトウェア全般
            
            ### 💡 Excel連携の利点
            - **正確性**: 公式の自治体コード表（総務省データ）に基づく選択
            - **効率性**: 自治体名から自動でコード変換・ファイル検索
            - **網羅性**: 全国47都道府県、1700+自治体に対応
            - **保守性**: Excelファイル更新により最新データに自動対応
            - **信頼性**: 団体コード（6桁）による確実な識別
            
            ### 📍 対応データ階層
            ```
            都道府県（47件）
            └── 市区町村（1700+件）
                └── 大字名（データ依存）
                    ├── 丁目名（任意）
                    │   └── 小字名（任意）
                    └── 小字名（任意、丁目なしの場合）
                        └── 地番（必須）
            ```
            
            ### 🔧 ファイル命名規則
            - **推奨形式**: `[自治体コード]_[地域名].zip`
            - **例**: `472011_那覇市.zip`、`47_沖縄県.zip`
            - **検索対象**: ファイル名に自治体コード（6桁）または都道府県コード（2桁）を含むファイル
            
            ### ⚠️ 注意事項
            - **Excel ファイル**: 000925835.xlsx が同じディレクトリに必要
            - **ネットワーク**: GitHub等からのファイル取得にインターネット接続が必要  
            - **ファイル形式**: ZIP圧縮されたShapefileセットに対応
            - **座標系**: 自動でWGS84（緯度経度）に変換してKML出力
            
            ### 🔧 トラブルシューティング
            - **自治体が見つからない**: Excel データの更新または自治体名の表記確認
            - **ファイルが見つからない**: 自治体コードがファイル名に含まれているか確認
            - **読み込みエラー**: Shapefileの形式、ZIP圧縮状態を確認
            - **座標エラー**: 元データの座標参照系（CRS）を確認
            """)

if __name__ == "__main__":
    main()
            # -*- coding: utf-8 -*-
"""
電子公図データ抽出Webアプリ (Streamlit版) - Excel自治体データ連携版
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
from urllib.parse import urlparse, urljoin
import re
from bs4 import BeautifulSoup
import json

# ページ設定
st.set_page_config(
    page_title="電子公図データ抽出ツール",
    page_icon="🗺️",
    layout="wide"
)

class KojiExcelMunicipalExtractor:
    def __init__(self):
        if 'gdf' not in st.session_state:
            st.session_state.gdf = None
        if 'web_files_cache' not in st.session_state:
            st.session_state.web_files_cache = {}
        if 'municipal_data' not in st.session_state:
            st.session_state.municipal_data = None
    
    def load_municipal_data_from_excel(self, excel_file_path):
        """Excelファイルから自治体データを読み込み"""
        try:
            # Excelファイルを読み込み
            df = pd.read_excel(excel_file_path, sheet_name=0)
            
            # 列名を正規化（改行文字を除去）
            df.columns = df.columns.str.replace('\r\n', '').str.replace('\n', '')
            
            # 必要な列が存在するかチェック
            required_columns = ['団体コード', '都道府県名（漢字）', '市区町村名（漢字）']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                st.error(f"必要な列が見つかりません: {missing_columns}")
                st.write("利用可能な列:", df.columns.tolist())
                return None
            
            # データをクリーニング
            df = df.dropna(subset=['団体コード'])
            df['団体コード'] = df['団体コード'].astype(str).str.zfill(6)
            
            # 市区町村名がNULLの行を除外（都道府県レベルのデータを除外）
            df = df.dropna(subset=['市区町村名（漢字）'])
            
            # 都道府県名と市区町村名を結合して完全な自治体名を作成
            df['完全自治体名'] = df['都道府県名（漢字）'] + df['市区町村名（漢字）']
            
            return df
            
        except Exception as e:
            st.error(f"Excelファイル読み込みエラー: {str(e)}")
            return None
    
    def get_prefectures_from_excel(self, municipal_df):
        """Excelデータから都道府県一覧を取得"""
        if municipal_df is None:
            return []
        
        try:
            prefectures = sorted(municipal_df['都道府県名（漢字）'].dropna().unique())
            return prefectures
        except Exception as e:
            st.error(f"都道府県一覧取得エラー: {str(e)}")
            return []
    
    def get_municipalities_by_prefecture_from_excel(self, municipal_df, prefecture_name):
        """Excelデータから指定都道府県の自治体一覧を取得"""
        if municipal_df is None:
            return []
        
        try:
            filtered_df = municipal_df[municipal_df['都道府県名（漢字）'] == prefecture_name]
            municipalities = sorted(filtered_df['市区町村名（漢字）'].dropna().unique())
            return municipalities
        except Exception as e:
            st.error(f"自治体一覧取得エラー: {str(e)}")
            return []
    
    def get_municipality_code_from_excel(self, municipal_df, prefecture_name, municipality_name):
        """Excelデータから自治体コードを取得"""
        if municipal_df is None:
            return None
        
        try:
            filtered_df = municipal_df[
                (municipal_df['都道府県名（漢字）'] == prefecture_name) &
                (municipal_df['市区町村名（漢字）'] == municipality_name)
            ]
            
            if len(filtered_df) > 0:
                return filtered_df.iloc[0]['団体コード']
            else:
                return None
        except Exception as e:
            st.error(f"自治体コード取得エラー: {str(e)}")
            return None
    
    def search_municipality_files(self, folder_url, municipality_code, file_extensions=None):
        """自治体コードに基づいてファイルを検索"""
        if file_extensions is None:
            file_extensions = ['.zip', '.shp']
        
        try:
            # フォルダ内のすべてのファイルを取得
            all_files = self.get_files_from_web_folder(folder_url, file_extensions)
            
            # 自治体コードが含まれるファイルをフィルタリング
            matching_files = []
            
            for file_info in all_files:
                file_name = file_info['name'].lower()
                
                # 自治体コードがファイル名に含まれているかチェック
                if str(municipality_code) in file_name:
                    matching_files.append(file_info)
                    continue
                
                # 自治体コードの最初の2桁（都道府県コード）もチェック
                prefecture_code = str(municipality_code)[:2]
                if prefecture_code in file_name:
                    matching_files.append(file_info)
            
            return matching_files
            
        except Exception as e:
            st.error(f"ファイル検索エラー: {str(e)}")
            return []
    
    def get_files_from_web_folder(self, folder_url, file_extensions=None):
        """Web上のフォルダからファイル一覧を取得"""
        if file_extensions is None:
            file_extensions = ['.zip', '.shp']
        
        try:
            # キャッシュをチェック
            cache_key = f"{folder_url}_{','.join(file_extensions)}"
            if cache_key in st.session_state.web_files_cache:
                return st.session_state.web_files_cache[cache_key]
            
            # GitHubのフォルダの場合
            if 'github.com' in folder_url:
                return self._get_github_folder_files(folder_url, file_extensions)
            
            # 通常のWebフォルダの場合
            return self._get_generic_web_folder_files(folder_url, file_extensions)
            
        except Exception as e:
            st.error(f"フォルダからのファイル取得に失敗しました: {str(e)}")
            return []
    
    def _get_github_folder_files(self, folder_url, file_extensions):
        """GitHubフォルダからファイル一覧を取得（GitHub API使用 + レート制限対策）"""
        try:
            # GitHub URLを解析
            parts = folder_url.replace('https://github.com/', '').split('/')
            if len(parts) < 2:
                raise Exception("無効なGitHub URLです")
            
            user = parts[0]
            repo = parts[1]
            
            # ブランチとパスを特定
            if len(parts) > 3 and parts[2] == 'tree':
                branch = parts[3]
                path = '/'.join(parts[4:]) if len(parts) > 4 else ''
            else:
                branch = 'main'
                path = '/'.join(parts[2:]) if len(parts) > 2 else ''
            
            # まずAPIを試行し、失敗した場合は代替方法を使用
            try:
                # GitHub API URL構築
                api_url = f"https://api.github.com/repos/{user}/{repo}/contents/{path}"
                if branch != 'main':
                    api_url += f"?ref={branch}"
                
                # GitHub APIトークンがある場合は使用
                headers = {}
                github_token = os.environ.get('GITHUB_TOKEN')
                if github_token:
                    headers['Authorization'] = f'token {github_token}'
                
                response = requests.get(api_url, headers=headers, timeout=30)
                
                if response.status_code == 403:
                    # レート制限の場合、代替方法を使用
                    st.warning("⚠️ GitHub APIのレート制限に達しました。代替方法でファイルを取得します...")
                    return self._get_github_files_alternative(user, repo, branch, path, file_extensions)
                
                response.raise_for_status()
                
                files_data = response.json()
                files = []
                
                for item in files_data:
                    if item['type'] == 'file':
                        file_name = item['name']
                        if any(file_name.lower().endswith(ext.lower()) for ext in file_extensions):
                            raw_url = item['download_url']
                            files.append({
                                'name': file_name,
                                'url': raw_url,
                                'size': item.get('size', 0),
                                'description': f"GitHubファイル ({item.get('size', 0)} bytes)"
                            })
                
                # キャッシュに保存
                cache_key = f"{folder_url}_{','.join(file_extensions)}"
                st.session_state.web_files_cache[cache_key] = files
                
                return files
                
            except requests.exceptions.RequestException as e:
                if "403" in str(e) or "rate limit" in str(e).lower():
                    st.warning("⚠️ GitHub APIのレート制限に達しました。代替方法でファイルを取得します...")
                    return self._get_github_files_alternative(user, repo, branch, path, file_extensions)
                else:
                    raise e
                
        except Exception as e:
            raise Exception(f"GitHub処理エラー: {str(e)}")
    
    def _get_github_files_alternative(self, user, repo, branch, path, file_extensions):
        """GitHub APIが使えない場合の代替方法"""
        try:
            web_url = f"https://github.com/{user}/{repo}/tree/{branch}/{path}"
            
            response = requests.get(web_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            files = []
            
            # GitHubのファイルリンクを検索
            file_links = soup.find_all('a', href=True)
            
            for link in file_links:
                href = link.get('href', '')
                link_text = link.get_text().strip()
                
                if '/blob/' in href and any(link_text.lower().endswith(ext.lower()) for ext in file_extensions):
                    raw_url = f"https://raw.githubusercontent.com{href.replace('/blob/', '/')}"
                    
                    files.append({
                        'name': link_text,
                        'url': raw_url,
                        'size': None,
                        'description': f"GitHubファイル（代替取得）"
                    })
            
            # 重複除去
            seen_names = set()
            unique_files = []
            for file_info in files:
                if file_info['name'] not in seen_names:
                    seen_names.add(file_info['name'])
                    unique_files.append(file_info)
            
            return unique_files
            
        except Exception as e:
            raise Exception(f"GitHub代替取得エラー: {str(e)}")
    
    def _get_generic_web_folder_files(self, folder_url, file_extensions):
        """一般的なWebフォルダからファイル一覧を取得"""
        try:
            response = requests.get(folder_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            files = []
            
            links = soup.find_all('a', href=True)
            
            for link in links:
                href = link['href']
                link_text = link.get_text().strip()
                
                if not href.startswith(('http://', 'https://')):
                    href = urljoin(folder_url, href)
                
                if any(href.lower().endswith(ext.lower()) for ext in file_extensions):
                    file_name = os.path.basename(urlparse(href).path)
                    if not file_name:
                        file_name = link_text
                    
                    files.append({
                        'name': file_name,
                        'url': href,
                        'size': None,
                        'description': f"Webファイル"
                    })
            
            return files
            
        except Exception as e:
            raise Exception(f"Webフォルダ処理エラー: {str(e)}")
    
    def download_file_from_url(self, url):
        """URLからファイルをダウンロード"""
        try:
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
                try:
                    with zipfile.ZipFile(file_obj, 'r') as zip_ref:
                        zip_ref.extractall(temp_dir)
                    
                    shp_files = [f for f in os.listdir(temp_dir) if f.endswith('.shp')]
                    
                    if shp_files:
                        shp_path = os.path.join(temp_dir, shp_files[0])
                        return gpd.read_file(shp_path)
                    else:
                        raise Exception("ZIPファイル内にSHPファイルが見つかりません")
                        
                except zipfile.BadZipFile:
                    file_obj.seek(0)
                    temp_file = os.path.join(temp_dir, "temp_file")
                    with open(temp_file, 'wb') as f:
                        f.write(file_obj.read())
                    
                    if url.lower().endswith('.shp'):
                        shp_file = temp_file + '.shp'
                        os.rename(temp_file, shp_file)
                        return gpd.read_file(shp_file)
                    else:
                        return gpd.read_file(temp_file)
                        
        except Exception as e:
            raise Exception(f"Shapefileの読み込みに失敗しました: {str(e)}")
    
    def create_kml_from_geodataframe(self, gdf, name="地番データ"):
        """GeoPandasデータフレームからKMLファイルを作成"""
        try:
            gdf_wgs84 = gdf.to_crs(epsg=4326)
            
            kml = ET.Element("kml", xmlns="http://www.opengis.net/kml/2.2")
            document = ET.SubElement(kml, "Document")
            doc_name = ET.SubElement(document, "name")
            doc_name.text = name
            
            style = ET.SubElement(document, "Style", id="PolygonStyle")
            line_style = ET.SubElement(style, "LineStyle")
            line_color = ET.SubElement(line_style, "color")
            line_color.text = "ff0000ff"
            line_width = ET.SubElement(line_style, "width")
            line_width.text = "2"
            
            poly_style = ET.SubElement(style, "PolyStyle")
            poly_color = ET.SubElement(poly_style, "color")
            poly_color.text = "3300ff00"
            
            for idx, row in gdf_wgs84.iterrows():
                placemark = ET.SubElement(document, "Placemark")
                
                pm_name = ET.SubElement(placemark, "name")
                if '地番' in row:
                    pm_name.text = str(row['地番'])
                else:
                    pm_name.text = f"地番_{idx}"
                
                description = ET.SubElement(placemark, "description")
                desc_text = ""
                for col in gdf_wgs84.columns:
                    if col != 'geometry':
                        desc_text += f"{col}: {row[col]}<br/>"
                description.text = desc_text
                
                style_url = ET.SubElement(placemark, "styleUrl")
                style_url.text = "#PolygonStyle"
                
                geom = row['geometry']
                if geom.geom_type == 'Polygon':
                    self._add_polygon_to_placemark(placemark, geom)
                elif geom.geom_type == 'MultiPolygon':
                    for poly in geom.geoms:
                        self._add_polygon_to_placemark(placemark, poly)
                elif geom.geom_type == 'Point':
                    self._add_point_to_placemark(placemark, geom)
            
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
        
        outer_boundary = ET.SubElement(kml_polygon, "outerBoundaryIs")
        linear_ring = ET.SubElement(outer_boundary, "LinearRing")
        coordinates = ET.SubElement(linear_ring, "coordinates")
        
        coord_str = ""
        for x, y in polygon.exterior.coords:
            coord_str += f"{x},{y},0 "
        coordinates.text = coord_str.strip()
        
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
        """データ抽出処理"""
        try:
            required_columns = ['大字名', '地番']
            missing_columns = [col for col in required_columns if col not in gdf.columns]
            
            if missing_columns:
                return None, None, f"必要な列が見つかりません: {missing_columns}"
            
            search_condition = (
                (gdf['大字名'] == oaza) & 
                (gdf['地番'] == chiban) &
                (gdf['大字名'].notna()) &
                (gdf['地番'].notna())
            )
            
            if chome is not None and chome != "選択なし" and '丁目名' in gdf.columns:
                search_condition = search_condition & (gdf['丁目名'] == chome) & (gdf['丁目名'].notna())
            
            if koaza is not None and koaza != "選択なし" and '小字名' in gdf.columns:
                search_condition = search_condition & (gdf['小字名'] == koaza) & (gdf['小字名'].notna())
            
            df = gdf[search_condition]
            
            if df.empty:
                return None, None, f"該当する筆が見つかりませんでした"
            
            # 中心点計算と周辺筆抽出
            cen = df.geometry.centroid
            cen_gdf = gpd.GeoDataFrame(geometry=cen)
            cen_gdf['x'] = cen_gdf.geometry.x
            cen_gdf['y'] = cen_gdf.geometry.y
            
            i1 = cen_gdf['x'] + range_m
            i2 = cen_gdf['x'] - range_m
            i3 = cen_gdf['y'] + range_m
            i4 = cen_gdf['y'] - range_m
            
            x1, y1 = i3.iloc[0], i1.iloc[0]
            x2, y2 = i4.iloc[0], i2.iloc[0]
            
            points = pd.DataFrame([
                [x1, y1], [x2, y2], [x1, y2], [x2, y1]
            ], columns=["lon", "lat"])
            
            geometry = [Point(xy) for xy in zip(points.lat, points.lon)]
            four_points_gdf = gpd.GeoDataFrame(points, geometry=geometry)
            sq = four_points_gdf.dissolve().convex_hull
            
            df1 = gpd.GeoDataFrame({'geometry': sq})
            df1 = df1.set_crs(gdf.crs)
            
            valid_data = gdf[(gdf['地番'].notna()) & (gdf['geometry'].notna())].copy()
            overlay_gdf = df1.overlay(valid_data, how='intersection')
            
            return df, overlay_gdf, f"対象筆: {len(df)}件, 周辺筆: {len(overlay_gdf)}件"
            
        except Exception as e:
            return None, None, f"エラー: {str(e)}")

def get_chome_options(gdf, selected_oaza):
    """指定された大字名に対応する丁目の選択肢を取得"""
    try:
        if '丁目名' not in gdf.columns:
            return None
        
        filtered_gdf = gdf[
            (gdf['大字名'] == selected_oaza) & 
            (gdf['大字名'].notna()) &
            (gdf['丁目名'].notna())
        ]
        
        if len(filtered_gdf) == 0:
            return None
        
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
        
        filter_condition = (
            (gdf['大字名'] == selected_oaza) & 
            (gdf['大字名'].notna()) &
            (gdf['小字名'].notna())
        )
        
        if selected_chome and selected_chome != "選択なし" and '丁目名' in gdf.columns:
            filter_condition = filter_condition & (gdf['丁目名'] == selected_chome) & (gdf['丁目名'].notna())
        
        filtered_gdf = gdf[filter_condition]
        
        if len(filtered_gdf) == 0:
            return None
        
        koaza_list = sorted(filtered_gdf['小字名'].unique())
        return koaza_list
        
    except Exception as e:
        st.error(f"小字名取得エラー: {str(e)}")
        return None

def main():
    st.title("🗺️ 電子公図データ抽出ツール（Excel自治体データ連携版）")
    st.markdown("---")
    
    extractor = KojiExcelMunicipalExtractor()
    
    # Excelファイルから自治体データを読み込み
    excel_file_path = "000925835.xlsx"  # Excelファイルのパス
    
    if st.session_state.municipal_data is None:
        with st.spinner("自治体データを初期化中..."):
            st.session_state.municipal_data = extractor.load_municipal_data_from_excel(excel_file_path)
            
            if st.session_state.municipal_data is not None:
                st.success(f"✅ 自治体データを読み込みました（{len(st.session_state.municipal_data)}件）")
            else:
                st.error("❌ 自治体データの読み込みに失敗しました")
    
    # サイドバー
    st.sidebar.header("🏛️ 自治体選択")
    
    if st.session_state.municipal_data is not None:
        # 都道府県選択
        prefectures = extractor.get_prefectures_from_excel(st.session_state.municipal_data)
        selected_prefecture = st.sidebar.selectbox(
            "都道府県を選択",
            ["選択してください"] + prefectures,
            help="データを取得したい都道府県を選択してください"
        )
        
        # 自治体選択
        selected_municipality = None
        municipality_code = None
        
        if selected_prefecture and selected_prefecture != "選択してください":
            municipalities = extractor.get_municipalities_by_prefecture_from_excel(
                st.session_state.municipal_data, selected_prefecture
            )
            
            if municipalities:
                selected_municipality = st.sidebar.selectbox(
                    "自治体を選択",
                    ["選択してください"] + municipalities,
                    help="データを取得したい自治体を選択してください"
                )
                
                if selected_municipality and selected_municipality != "選択してください":
                    municipality_code = extractor.get_municipality_code_from_excel(
                        st.session_state.municipal_data, selected_prefecture, selected_municipality
                    )
                    
                    if municipality_code:
                        st.sidebar.success(f"✅ 自治体コード: {municipality_code}")
                        st.sidebar.info(f"📍 選択: {selected_prefecture} {selected_municipality}")
                    else:
                        st.sidebar.error("❌ 自治体コードが見つかりません")
            else:
                st.sidebar.warning("該当する自治体が見つかりません")
    else:
        st.sidebar.error("❌ 自治体データが読み込まれていません")
    
    st.sidebar.markdown("---")
    
    # データフォルダ設定
    st.sidebar.header("📂 データフォルダ設定")
    
    # デフォルトのデータフォルダURL
    default_data_folder = "https://github.com/kentashimoji/koji-data-extractor/tree/main"
    
    data_folder_url = st.sidebar.text_input(
        "データフォルダURL",
        value=default_data_folder,
        help="Shapefileが格納されているフォルダのURLを入力してください"
    )
    
    # 自治体コードに基づくファイル検索
    matching_files = []
    if municipality_code and data_folder_url:
        if st.sidebar.button("🔍 該当ファイルを検索", type="primary"):
            with st.spinner(f"{selected_municipality}のファイルを検索中..."):
                try:
                    matching_files = extractor.search_municipality_files(
                        data_folder_url, 
                        municipality_code
                    )
                    
                    if matching_files:
                        st.sidebar.success(f"✅ {len(matching_files)}個のファイルが見つかりました")
                        st.session_state.matching_files = matching_files
                        st.session_state.selected_municipality = selected_municipality
                        st.session_state.municipality_code = municipality_code
                    else:
                        st.sidebar.warning(f"❌ {selected_municipality}（コード: {municipality_code}）に該当するファイルが見つかりませんでした")
                
                except Exception as e:
                    st.sidebar.error(f"❌ 検索エラー: {str(e)}")
    
    # 検索結果からファイル選択
    if 'matching_files'