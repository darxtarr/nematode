//! Reflex Binary Format
//!
//! Binary container for trained reflex models.
//! Layout: [Header][Model][Bounds][Metadata][Checksum]

use serde::{Deserialize, Serialize};
use std::io::{self, Write};

/// Magic bytes: "NEM1"
pub const MAGIC: [u8; 4] = *b"NEM1";

/// Current format version
pub const VERSION: u16 = 1;

/// Model type discriminant
#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ModelType {
    DecisionTree = 0,
    Linear = 1,
    // Future: MLP = 2,
}

/// Reflex file header (fixed size)
#[repr(C)]
#[derive(Debug, Clone, Copy)]
pub struct ReflexHeader {
    pub magic: [u8; 4],
    pub version: u16,
    pub model_type: u8,
    pub feature_count: u8,
    pub output_count: u8,
    pub created_at_unix: u64,
    pub model_size_bytes: u32,
    pub bounds_size_bytes: u32,
    pub metadata_size_bytes: u32,
}

impl ReflexHeader {
    const SIZE: usize = 29; // 4 + 2 + 1 + 1 + 1 + 8 + 4 + 4 + 4

    pub fn new(
        model_type: ModelType,
        feature_count: u8,
        output_count: u8,
        created_at_unix: u64,
        model_size_bytes: u32,
        bounds_size_bytes: u32,
        metadata_size_bytes: u32,
    ) -> Self {
        Self {
            magic: MAGIC,
            version: VERSION,
            model_type: model_type as u8,
            feature_count,
            output_count,
            created_at_unix,
            model_size_bytes,
            bounds_size_bytes,
            metadata_size_bytes,
        }
    }

    pub fn to_bytes(&self) -> [u8; Self::SIZE] {
        let mut buf = Vec::with_capacity(Self::SIZE);
        buf.extend_from_slice(&self.magic);
        buf.extend_from_slice(&self.version.to_le_bytes());
        buf.push(self.model_type);
        buf.push(self.feature_count);
        buf.push(self.output_count);
        buf.extend_from_slice(&self.created_at_unix.to_le_bytes());
        buf.extend_from_slice(&self.model_size_bytes.to_le_bytes());
        buf.extend_from_slice(&self.bounds_size_bytes.to_le_bytes());
        buf.extend_from_slice(&self.metadata_size_bytes.to_le_bytes());

        let mut result = [0u8; Self::SIZE];
        result.copy_from_slice(&buf);
        result
    }

    pub fn from_bytes(bytes: &[u8]) -> io::Result<Self> {
        if bytes.len() < Self::SIZE {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "Header too short",
            ));
        }

        let mut offset = 0;

        let mut magic = [0u8; 4];
        magic.copy_from_slice(&bytes[offset..offset + 4]);
        offset += 4;

        let version = u16::from_le_bytes([bytes[offset], bytes[offset + 1]]);
        offset += 2;

        let model_type = bytes[offset];
        offset += 1;

        let feature_count = bytes[offset];
        offset += 1;

        let output_count = bytes[offset];
        offset += 1;

        let created_at_unix = u64::from_le_bytes([
            bytes[offset],
            bytes[offset + 1],
            bytes[offset + 2],
            bytes[offset + 3],
            bytes[offset + 4],
            bytes[offset + 5],
            bytes[offset + 6],
            bytes[offset + 7],
        ]);
        offset += 8;

        let model_size_bytes = u32::from_le_bytes([
            bytes[offset],
            bytes[offset + 1],
            bytes[offset + 2],
            bytes[offset + 3],
        ]);
        offset += 4;

        let bounds_size_bytes = u32::from_le_bytes([
            bytes[offset],
            bytes[offset + 1],
            bytes[offset + 2],
            bytes[offset + 3],
        ]);
        offset += 4;

        let metadata_size_bytes = u32::from_le_bytes([
            bytes[offset],
            bytes[offset + 1],
            bytes[offset + 2],
            bytes[offset + 3],
        ]);

        Ok(Self {
            magic,
            version,
            model_type,
            feature_count,
            output_count,
            created_at_unix,
            model_size_bytes,
            bounds_size_bytes,
            metadata_size_bytes,
        })
    }

    pub fn validate(&self) -> Result<(), String> {
        if self.magic != MAGIC {
            return Err(format!("Invalid magic: {:?}", self.magic));
        }
        if self.version != VERSION {
            return Err(format!("Unsupported version: {}", self.version));
        }
        Ok(())
    }
}

/// Decision tree node (for ModelType::DecisionTree)
#[repr(C)]
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct TreeNode {
    /// Feature index to split on (0xFF = leaf)
    pub feature_idx: u8,
    /// Threshold for split (or leaf value if leaf)
    pub threshold: f32,
    /// Left child index (or unused if leaf)
    pub left: u16,
    /// Right child index (or unused if leaf)
    pub right: u16,
}

impl TreeNode {
    pub fn is_leaf(&self) -> bool {
        self.feature_idx == 0xFF
    }

    pub fn leaf(value: f32) -> Self {
        Self {
            feature_idx: 0xFF,
            threshold: value,
            left: 0,
            right: 0,
        }
    }

    pub fn split(feature_idx: u8, threshold: f32, left: u16, right: u16) -> Self {
        Self {
            feature_idx,
            threshold,
            left,
            right,
        }
    }
}

/// Output bounds for clamping
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OutputBounds {
    pub min: Vec<f32>,
    pub max: Vec<f32>,
}

/// Metadata (YAML-encoded)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReflexMetadata {
    pub created_at: String,
    pub trainer_commit: String,
    pub feature_schema: String,
    pub telemetry_hash: String,
    pub lambda: f32,
    pub notes: String,
}

/// Complete reflex model
#[derive(Debug, Clone)]
pub struct Reflex {
    pub header: ReflexHeader,
    pub trees: Vec<Vec<TreeNode>>, // one tree per output
    pub bounds: OutputBounds,
    pub metadata: ReflexMetadata,
}

impl Reflex {
    /// Serialize to binary format
    pub fn to_bytes(&self) -> io::Result<Vec<u8>> {
        let mut buf = Vec::new();

        // Serialize model (trees)
        let model_bytes = serde_json::to_vec(&self.trees)
            .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;

        // Serialize bounds
        let bounds_bytes = serde_json::to_vec(&self.bounds)
            .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;

        // Serialize metadata
        let metadata_bytes = serde_json::to_vec(&self.metadata)
            .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;

        // Build header
        let header = ReflexHeader::new(
            ModelType::DecisionTree,
            self.header.feature_count,
            self.header.output_count,
            self.header.created_at_unix,
            model_bytes.len() as u32,
            bounds_bytes.len() as u32,
            metadata_bytes.len() as u32,
        );

        // Write header
        buf.write_all(&header.to_bytes())?;

        // Write model
        buf.write_all(&model_bytes)?;

        // Write bounds
        buf.write_all(&bounds_bytes)?;

        // Write metadata
        buf.write_all(&metadata_bytes)?;

        // Compute and write CRC32
        let crc = crc32fast::hash(&buf);
        buf.write_all(&crc.to_le_bytes())?;

        Ok(buf)
    }

    /// Deserialize from binary format
    pub fn from_bytes(data: &[u8]) -> io::Result<Self> {
        if data.len() < ReflexHeader::SIZE + 4 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "Data too short",
            ));
        }

        // Extract and validate checksum
        let payload_len = data.len() - 4;
        let payload = &data[..payload_len];
        let expected_crc = u32::from_le_bytes([
            data[payload_len],
            data[payload_len + 1],
            data[payload_len + 2],
            data[payload_len + 3],
        ]);
        let actual_crc = crc32fast::hash(payload);
        if actual_crc != expected_crc {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("CRC mismatch: expected {}, got {}", expected_crc, actual_crc),
            ));
        }

        // Parse header
        let header = ReflexHeader::from_bytes(&payload[..ReflexHeader::SIZE])?;
        header.validate().map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;

        let mut offset = ReflexHeader::SIZE;

        // Parse model
        let model_end = offset + header.model_size_bytes as usize;
        let trees: Vec<Vec<TreeNode>> = serde_json::from_slice(&payload[offset..model_end])
            .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;
        offset = model_end;

        // Parse bounds
        let bounds_end = offset + header.bounds_size_bytes as usize;
        let bounds: OutputBounds = serde_json::from_slice(&payload[offset..bounds_end])
            .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;
        offset = bounds_end;

        // Parse metadata
        let metadata_end = offset + header.metadata_size_bytes as usize;
        let metadata: ReflexMetadata = serde_json::from_slice(&payload[offset..metadata_end])
            .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;

        Ok(Reflex {
            header,
            trees,
            bounds,
            metadata,
        })
    }

    /// Run inference on a single sample
    pub fn infer(&self, features: &[f32]) -> Vec<f32> {
        assert_eq!(
            features.len(),
            self.header.feature_count as usize,
            "Feature count mismatch"
        );

        let mut outputs = Vec::with_capacity(self.trees.len());

        for tree in &self.trees {
            let value = self.eval_tree(tree, features);
            outputs.push(value);
        }

        // Clamp to bounds
        for (i, output) in outputs.iter_mut().enumerate() {
            *output = output.clamp(self.bounds.min[i], self.bounds.max[i]);
        }

        outputs
    }

    fn eval_tree(&self, tree: &[TreeNode], features: &[f32]) -> f32 {
        let mut node_idx = 0;
        loop {
            let node = &tree[node_idx];
            if node.is_leaf() {
                return node.threshold;
            }
            let feature_val = features[node.feature_idx as usize];
            node_idx = if feature_val <= node.threshold {
                node.left as usize
            } else {
                node.right as usize
            };
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_header_roundtrip() {
        let h = ReflexHeader::new(ModelType::DecisionTree, 10, 2, 1728000000, 100, 50, 200);
        let bytes = h.to_bytes();
        let h2 = ReflexHeader::from_bytes(bytes);
        assert_eq!(h.magic, h2.magic);
        assert_eq!(h.version, h2.version);
        assert_eq!(h.model_type, h2.model_type);
        assert_eq!(h.feature_count, h2.feature_count);
    }

    #[test]
    fn test_reflex_roundtrip() {
        // Simple tree: if feature[0] <= 0.5 then 10.0 else 20.0
        let tree = vec![
            TreeNode::split(0, 0.5, 1, 2),
            TreeNode::leaf(10.0),
            TreeNode::leaf(20.0),
        ];

        let reflex = Reflex {
            header: ReflexHeader::new(ModelType::DecisionTree, 1, 1, 1728000000, 0, 0, 0),
            trees: vec![tree],
            bounds: OutputBounds {
                min: vec![0.0],
                max: vec![100.0],
            },
            metadata: ReflexMetadata {
                created_at: "2025-10-06T12:00:00Z".to_string(),
                trainer_commit: "test".to_string(),
                feature_schema: "v1".to_string(),
                telemetry_hash: "abcd".to_string(),
                lambda: 0.1,
                notes: "test reflex".to_string(),
            },
        };

        // Serialize and deserialize
        let bytes = reflex.to_bytes().unwrap();
        let reflex2 = Reflex::from_bytes(&bytes).unwrap();

        // Test inference
        let out1 = reflex2.infer(&[0.3]);
        assert_eq!(out1[0], 10.0);

        let out2 = reflex2.infer(&[0.7]);
        assert_eq!(out2[0], 20.0);
    }
}
