# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
services/chunk_manager.py
=========================
Chunk management utility for mutual fund data.

Provides:
- Chunk validation and health checks
- Chunk repair and remediation
- Chunk metadata tracking
- Chunk statistics and reporting
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
import pandas as pd

logger = logging.getLogger(__name__)


class ChunkManager:
    """Manages mutual fund data chunks."""
    
    def __init__(self, chunks_dir: str):
        """
        Initialize chunk manager.
        
        Args:
            chunks_dir: Path to chunks directory
        """
        self.chunks_dir = Path(chunks_dir)
        self.manifest_path = self.chunks_dir / "manifest.json"
        self.manifest = None
        self.chunk_files = []
        
        if not self.chunks_dir.exists():
            raise FileNotFoundError(f"Chunks directory not found: {self.chunks_dir}")
        
        self._load_manifest()
    
    def _load_manifest(self) -> None:
        """Load chunk manifest."""
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path) as f:
                    self.manifest = json.load(f)
                logger.info(f"✓ Loaded manifest: {self.manifest['chunk_count']} chunks")
            except Exception as e:
                logger.warning(f"Could not load manifest: {e}")
    
    def get_chunk_files(self) -> List[Path]:
        """Get all chunk files."""
        self.chunk_files = sorted(self.chunks_dir.glob('mutual_fund_data_chunk_*.csv'))
        return self.chunk_files
    
    def get_health_report(self) -> Dict[str, Any]:
        """
        Generate comprehensive health report for chunks.
        
        Returns:
            Health report dict
        """
        report = {
            'timestamp': pd.Timestamp.now().isoformat(),
            'total_chunks': 0,
            'healthy_chunks': 0,
            'corrupted_chunks': 0,
            'missing_chunks': 0,
            'total_rows': 0,
            'issues': [],
            'chunk_details': []
        }
        
        if not self.manifest:
            report['issues'].append('Manifest not found or invalid')
            return report
        
        expected_chunks = self.manifest.get('chunk_count', 0)
        expected_rows = self.manifest.get('original_rows', 0)
        
        report['total_chunks'] = expected_chunks
        
        # Check each chunk
        for chunk_info in self.manifest.get('chunks', []):
            chunk_file = Path(chunk_info['filepath'])
            
            detail = {
                'filename': chunk_info['filename'],
                'expected_rows': chunk_info.get('rows', 0),
                'status': 'unknown'
            }
            
            if not chunk_file.exists():
                detail['status'] = 'missing'
                report['missing_chunks'] += 1
                report['issues'].append(f"Missing: {chunk_info['filename']}")
            else:
                try:
                    df = pd.read_csv(chunk_file)
                    actual_rows = len(df)
                    detail['actual_rows'] = actual_rows
                    
                    # Check required columns
                    required_cols = ['Scheme_Name', 'AMC', 'Average_AUM_Cr']
                    missing_cols = set(required_cols) - set(df.columns)
                    
                    if missing_cols:
                        detail['status'] = 'corrupted'
                        report['corrupted_chunks'] += 1
                        report['issues'].append(f"Missing columns in {chunk_info['filename']}: {missing_cols}")
                    elif actual_rows != detail['expected_rows']:
                        detail['status'] = 'mismatched'
                        report['issues'].append(f"Row mismatch in {chunk_info['filename']}: expected {detail['expected_rows']}, got {actual_rows}")
                    else:
                        detail['status'] = 'healthy'
                        report['healthy_chunks'] += 1
                        report['total_rows'] += actual_rows
                
                except Exception as e:
                    detail['status'] = 'error'
                    detail['error'] = str(e)
                    report['corrupted_chunks'] += 1
                    report['issues'].append(f"Error reading {chunk_info['filename']}: {e}")
            
            report['chunk_details'].append(detail)
        
        # Overall status
        report['overall_status'] = 'healthy' if report['corrupted_chunks'] == 0 and report['missing_chunks'] == 0 else 'degraded'
        
        return report
    
    def repair_chunk(self, chunk_num: int, source_df: Optional[pd.DataFrame] = None) -> bool:
        """
        Repair a corrupted chunk.
        
        Args:
            chunk_num: Chunk number to repair (1-indexed)
            source_df: Source DataFrame (if available from combined data)
        
        Returns:
            True if repair successful
        """
        if not self.manifest:
            logger.error("Manifest not available for repair")
            return False
        
        # Find chunk info
        chunk_info = None
        for c in self.manifest.get('chunks', []):
            if c.get('chunk_num') == chunk_num:
                chunk_info = c
                break
        
        if not chunk_info:
            logger.error(f"Chunk {chunk_num} not found in manifest")
            return False
        
        try:
            chunk_file = Path(chunk_info['filepath'])
            start_row = chunk_info.get('start_row', 0) - 1  # Convert to 0-indexed
            end_row = chunk_info.get('end_row', 0)
            
            if source_df is not None:
                # Use provided source data
                chunk_data = source_df.iloc[start_row:end_row]
            else:
                # Try to recover from backup or recombine others
                logger.warning(f"Attempting to recover chunk {chunk_num} without source data")
                return False
            
            # Write repaired chunk
            chunk_data.to_csv(chunk_file, index=False)
            logger.info(f"✓ Repaired chunk {chunk_num}: {chunk_file.name}")
            
            return True
        except Exception as e:
            logger.error(f"Error repairing chunk {chunk_num}: {e}")
            return False
    
    def get_chunk_statistics(self) -> Dict[str, Any]:
        """Get statistics about chunks."""
        stats = {
            'total_chunks': 0,
            'total_rows': 0,
            'total_size_mb': 0,
            'chunk_rows': [],
            'chunk_sizes_mb': [],
            'avg_chunk_size_mb': 0,
            'avg_chunk_rows': 0
        }
        
        if not self.manifest:
            return stats
        
        chunks_info = self.manifest.get('chunks', [])
        stats['total_chunks'] = len(chunks_info)
        
        for chunk_info in chunks_info:
            rows = chunk_info.get('rows', 0)
            size_mb = chunk_info.get('size_mb', 0)
            
            stats['total_rows'] += rows
            stats['total_size_mb'] += size_mb
            stats['chunk_rows'].append(rows)
            stats['chunk_sizes_mb'].append(size_mb)
        
        if stats['total_chunks'] > 0:
            stats['avg_chunk_rows'] = stats['total_rows'] // stats['total_chunks']
            stats['avg_chunk_size_mb'] = stats['total_size_mb'] / stats['total_chunks']
        
        return stats
    
    def get_chunk_by_scheme(self, scheme_name: str) -> Optional[Dict[str, Any]]:
        """
        Find which chunk contains a specific scheme.
        
        Args:
            scheme_name: Name of scheme to find
        
        Returns:
            Chunk info dict or None
        """
        for chunk_file in self.get_chunk_files():
            try:
                df = pd.read_csv(chunk_file)
                if scheme_name in df['Scheme_Name'].values:
                    return {
                        'filename': chunk_file.name,
                        'filepath': str(chunk_file),
                        'rows': len(df),
                        'size_mb': chunk_file.stat().st_size / (1024 * 1024)
                    }
            except Exception as e:
                logger.warning(f"Error searching {chunk_file.name}: {e}")
        
        return None
    
    def list_chunks_by_amc(self, amc_name: str) -> List[Dict[str, Any]]:
        """
        Get all chunks containing a specific AMC.
        
        Args:
            amc_name: AMC name to search for
        
        Returns:
            List of chunk info dicts
        """
        results = []
        
        for chunk_file in self.get_chunk_files():
            try:
                df = pd.read_csv(chunk_file)
                if amc_name in df['AMC'].values:
                    results.append({
                        'filename': chunk_file.name,
                        'filepath': str(chunk_file),
                        'rows': len(df),
                        'amc_schemes': len(df[df['AMC'] == amc_name]['Scheme_Name'].unique())
                    })
            except Exception as e:
                logger.warning(f"Error searching {chunk_file.name}: {e}")
        
        return results
    
    def export_chunk_report(self, output_file: Optional[str] = None) -> str:
        """
        Export comprehensive chunk report to JSON.
        
        Args:
            output_file: Output filename (defaults to chunk_report.json)
        
        Returns:
            Path to exported report
        """
        if output_file is None:
            output_file = self.chunks_dir / "chunk_report.json"
        else:
            output_file = Path(output_file)
        
        report = {
            'timestamp': pd.Timestamp.now().isoformat(),
            'health': self.get_health_report(),
            'statistics': self.get_chunk_statistics(),
            'manifest': self.manifest
        }
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"✓ Chunk report exported to {output_file}")
        return str(output_file)


# Singleton instance
_chunk_manager_instance: Optional[ChunkManager] = None


def get_chunk_manager(chunks_dir: Optional[str] = None) -> Optional[ChunkManager]:
    """Get or create chunk manager instance."""
    global _chunk_manager_instance
    
    if chunks_dir:
        _chunk_manager_instance = ChunkManager(chunks_dir)
    elif _chunk_manager_instance is None:
        # Try to find chunks directory automatically
        from pathlib import Path
        project_root = Path(__file__).resolve().parent.parent.parent
        chunks_dir = project_root / "data" / "source_docs" / "chunks"
        
        if chunks_dir.exists():
            _chunk_manager_instance = ChunkManager(str(chunks_dir))
    
    return _chunk_manager_instance
