import test from 'node:test';
import assert from 'node:assert/strict';
import {matchingVideo, uploadItems, isLivePackage} from '../live-upload.mjs';
const file=(name,type='')=>({name,type});
test('iPhone pair becomes one attachment regardless of picker order and empty MIME',()=>{
 const image=file('IMG_0011.HEIC'),video=file('img_0011.MOV');
 const files=[video,image];
 assert.equal(matchingVideo(image,files),video);
 const items=uploadItems(files,[{enabled:false},{enabled:true,pair:video}]);
 assert.equal(items.length,1);assert.equal(items[0].file,image);
});
test('ambiguous names and unrelated videos are not silently paired',()=>{
 const image=file('IMG_1.jpg'),movie=file('IMG_1.mov');
 assert.equal(matchingVideo(image,[image,movie,file('IMG_1.mp4')]),null);
 assert.equal(matchingVideo(image,[image,movie,file('IMG_1.heic')]),null);
 assert.equal(matchingVideo(image,[image,file('IMG_2.mov')]),null);
});
test('opt out excludes paired movie; removal restores standalone video',()=>{
 const image=file('a.jpg'),movie=file('a.mov'),files=[image,movie];
 assert.equal(uploadItems(files,[{enabled:false,pair:movie},{}]).length,1);
 assert.equal(uploadItems(files,[{enabled:false,pair:null},{}]).length,2);
 assert.ok(isLivePackage(file('A.LIVP')));
});
